"""Assistant-only causal loss with bounded vocabulary-projection memory."""


def chunked_assistant_loss(hidden, head, input_ids, assistant_mask, softcap=None, chunk_size=64):
    """Exact mean CE at supervised next-token positions; recompute head on backward.

    Context hidden states still attend to the full prompt. Only the vocabulary
    projection and float32 CE are chunked; prompt tokens are never supervised.
    """
    import torch
    from torch.utils.checkpoint import checkpoint
    if chunk_size < 1: raise ValueError('chunk_size must be positive')
    positions=torch.nonzero(assistant_mask[0,1:],as_tuple=False).flatten()
    if not positions.numel(): raise ValueError('No supervised next tokens')
    def project_loss(states,targets):
        logits=head(states)
        if softcap is not None:
            logits=torch.tanh(logits/softcap)*softcap
        return torch.nn.functional.cross_entropy(logits.float(),targets,reduction='sum')
    total=hidden.new_zeros((),dtype=torch.float32)
    for indices in positions.split(chunk_size):
        states=hidden[0,indices,:]
        targets=input_ids[0,indices+1]
        total=total+checkpoint(project_loss,states,targets,use_reentrant=False)
    return total/positions.numel()


def gemma_assistant_loss(model,input_ids,assistant_mask,chunk_size=64):
    """Use the adapted Gemma backbone without constructing full-sequence logits."""
    import torch
    base=model.get_base_model()
    outputs=base.model(input_ids=input_ids,attention_mask=torch.ones_like(input_ids),
                       use_cache=False,return_dict=True)
    return chunked_assistant_loss(outputs.last_hidden_state,base.lm_head,input_ids,
        assistant_mask,base.config.get_text_config().final_logit_softcapping,chunk_size)


def backward_example(model,row,total_tokens,chunk_size=64):
    """Offload saved forward activations and free per-example graphs on return."""
    import torch
    device=model.get_input_embeddings().weight.device
    ids=torch.tensor([row['input_ids']],device=device)
    mask=torch.tensor([row['assistant_mask']],device=device,dtype=torch.bool)
    # Checkpoint recomputation still runs on GPU; only saved tensors live on CPU.
    with torch.autograd.graph.save_on_cpu(pin_memory=True):
        with torch.autocast(device_type=device.type,dtype=torch.bfloat16):
            loss=gemma_assistant_loss(model,ids,mask,chunk_size)
            weight=sum(row['assistant_mask'][1:])/total_tokens
            weighted=loss*weight
    if not torch.isfinite(weighted.detach()): raise ValueError('Nonfinite SFT loss')
    weighted.backward()
    return float(weighted.detach())
