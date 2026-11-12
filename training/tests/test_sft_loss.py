import unittest
import torch
from costagent.sft_loss import chunked_assistant_loss

class ChunkedLossTests(unittest.TestCase):
    def test_dense_loss_and_gradients(self):
        for softcap in (None, 3.):
            for chunk_size in (1, 3, 64):
                torch.manual_seed(42)
                hidden=torch.randn(1,9,5,requires_grad=True)
                head=torch.nn.Linear(5,13,bias=False)
                ids=torch.tensor([[1,2,3,4,5,6,7,8,9]])
                mask=torch.tensor([[False,False,True,True,False,True,False,True,True]])
                logits=head(hidden[:,:-1])
                if softcap: logits=torch.tanh(logits/softcap)*softcap
                labels=ids[:,1:].clone();labels[~mask[:,1:]]=-100
                dense=torch.nn.functional.cross_entropy(logits.flatten(0,1),labels.flatten())
                dense.backward();expected_hidden=hidden.grad.clone();expected_head=head.weight.grad.clone()
                hidden.grad=None;head.weight.grad=None
                actual=chunked_assistant_loss(hidden,head,ids,mask,softcap,chunk_size)
                actual.backward()
                torch.testing.assert_close(actual,dense)
                torch.testing.assert_close(hidden.grad,expected_hidden)
                torch.testing.assert_close(head.weight.grad,expected_head)

    def test_empty_mask(self):
        with self.assertRaises(ValueError):
            chunked_assistant_loss(torch.zeros(1,3,2),torch.nn.Linear(2,4),
                                   torch.zeros(1,3,dtype=torch.long),torch.zeros(1,3,dtype=torch.bool))

    def test_projection_is_bounded(self):
        sizes=[]
        head=torch.nn.Linear(4,10)
        head.register_forward_pre_hook(lambda module,args:sizes.append(args[0].shape[0]))
        hidden=torch.randn(1,20,4,requires_grad=True)
        loss=chunked_assistant_loss(hidden,head,torch.zeros(1,20,dtype=torch.long),
                                   torch.ones(1,20,dtype=torch.bool),chunk_size=3)
        loss.backward()
        self.assertTrue(sizes)
        self.assertLessEqual(max(sizes),3)
