import unittest
import requests
import docker
import json

IP = '0.0.0.0'
PORT = '5000'
img_tag = 'test-img'
container_name = 'test-container'
client = docker.from_env(timeout=86400)
item_id = 'doc1234'
page = 0
rpp = 10


class TestApp(unittest.TestCase):

    def test_01_run(self):
        url = 'http://' + IP + ':' + PORT + '/test'
        res = requests.get(url)
        self.assertEqual(res.status_code, 200)

    def test_02_indexing(self):
        url = 'http://' + IP + ':' + PORT + '/index'
        res = requests.get(url)
        self.assertEqual(res.status_code, 200)

    def test_03_recommendation_keys(self):
        url = 'http://' + IP + ':' + PORT + '/recommendation/datasets?item_id=' + item_id + '&page=' + str(page) + '&rpp=' + str(rpp)
        res = requests.get(url)
        keys = json.loads(res.content).keys()
        self.assertTrue('itemlist' in keys)
        self.assertTrue('num_found' in keys)
        self.assertTrue('page' in keys)
        self.assertTrue('item_id' in keys)
        self.assertTrue('rpp' in keys)

    def test_04_recommendation_key_contents(self):
        url = 'http://' + IP + ':' + PORT + '/recommendation/datasets?item_id=' + item_id + '&page=' + str(page) + '&rpp=' + str(rpp)
        res = requests.get(url)
        content = json.loads(res.content)
        self.assertEqual(content.get('page'), page)
        self.assertEqual(content.get('rpp'), rpp)
        self.assertEqual(content.get('item_id'), item_id)

    def test_05_recommendation_not_empty(self):
        url = 'http://' + IP + ':' + PORT + '/recommendation/datasets?item_id=' + item_id + '&page=' + str(page) + '&rpp=' + str(rpp)
        res = requests.get(url)
        content = json.loads(res.content)
        self.assertGreater(len(content.get('itemlist')), 0)

    def test_06_recommendation_length(self):
        url = 'http://' + IP + ':' + PORT + '/recommendation/datasets?item_id=' + item_id + '&page=' + str(page) + '&rpp=' + str(rpp)
        res = requests.get(url)
        content = json.loads(res.content)
        self.assertEqual(len(content.get('itemlist')), content.get('num_found'))


if __name__ == '__main__':
    unittest.main()
