import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from costagent.dpo_monitor import training_metrics,choose_checkpoint
from costagent.dpo_dev_eval import candidates,freeze_manifest,stop_owned

class MonitorTests(unittest.TestCase):
    def test_training_metrics_do_not_claim_validation(self):
        rows={k:dict(turns=[dict(assistant_mask=[0,1])]) for k in ('c','r')}
        pairs=[dict(chosen='c',rejected='r')]
        report=training_metrics({'c':-1.,'r':-1.},{'c':-1.,'r':-1.},pairs,rows)
        self.assertEqual(report['preference_accuracy'],.5)
        self.assertEqual(report['split'],'training_pairs_not_validation')
        report=training_metrics({'c':-1.,'r':-1e9},{'c':-1.,'r':-1.},pairs,rows)
        self.assertEqual(report['preference_accuracy'],1.)
        self.assertAlmostEqual(report['mean_loss'],1.)

    def test_checkpoint_selection_keeps_baseline_on_tie(self):
        baseline=dict(checkpoint='sft',solved=0,mean_calls_solved=None)
        failed=dict(checkpoint='epoch-1',solved=0,mean_calls_solved=None)
        good=dict(checkpoint='epoch-2',solved=1,mean_calls_solved=10.)
        costly=dict(checkpoint='epoch-3',solved=1,mean_calls_solved=20.)
        self.assertIs(choose_checkpoint([baseline,failed]),baseline)
        self.assertIs(choose_checkpoint([baseline,good,costly]),good)

    def test_dev_candidates_exclude_all_training_successes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest=root/'manifest.json'
            manifest.write_text(json.dumps(dict(attempts=[dict(task_id='seen',resolved=True),
                dict(task_id='seen',resolved=False),dict(task_id='unseen',resolved=False),dict(task_id='unknown',resolved=None)])))
            for task in ('seen','unseen','unknown'):
                p=root/'tasks'/task;p.mkdir(parents=True)
                (p/'grading_spec.json').write_text(json.dumps(dict(repo=task,image_name=task)))
            with patch('costagent.dpo_dev_eval.TRAIN',manifest):
                self.assertEqual([r['task_id'] for r in candidates()],['unseen'])

    def test_manifest_uses_distinct_repos_and_cached_images(self):
        rows=[dict(task_id=str(i),repo=str(i//2),image='image') for i in range(8)]
        client=Mock()
        with tempfile.TemporaryDirectory() as d,patch('costagent.dpo_dev_eval.candidates',return_value=rows),patch('costagent.dpo_dev_eval.write_json'):
            manifest=freeze_manifest(Path(d)/'manifest.json',client,4)
        self.assertEqual(len({r['repo'] for r in manifest['tasks']}),4)
        self.assertFalse(manifest['images_pulled'])
        client.images.pull.assert_not_called()

    def test_only_owned_live_process_is_signaled(self):
        process=Mock();process.pid=123;process.poll.return_value=None
        with patch('costagent.dpo_dev_eval.os.killpg') as kill:
            stop_owned(process)
            self.assertEqual(kill.call_args.args[0],123)
        process.poll.return_value=0
        with patch('costagent.dpo_dev_eval.os.killpg') as kill:
            stop_owned(process);kill.assert_not_called()


class DockerEnvironmentTests(unittest.TestCase):
    def test_recorded_daemon_used_for_client_and_worker_environment(self):
        from costagent.dpo_dev_eval import docker_environment
        original={'PATH':'/bin'}
        env,expected=docker_environment(original,{'docker_host':'unix:///tmp/project/docker.sock','docker_data_root':'/tmp/project/data'})
        self.assertEqual(env['DOCKER_HOST'],'unix:///tmp/project/docker.sock')
        self.assertEqual(expected,'/tmp/project/data')
        self.assertNotIn('DOCKER_HOST',original)

    def test_explicit_docker_host_is_preserved(self):
        from costagent.dpo_dev_eval import docker_environment
        env,expected=docker_environment({'DOCKER_HOST':'unix:///custom/docker.sock'},
            {'docker_host':'unix:///tmp/project/docker.sock','docker_data_root':'/tmp/project/data'})
        self.assertEqual(env['DOCKER_HOST'],'unix:///custom/docker.sock')
        self.assertIsNone(expected)
