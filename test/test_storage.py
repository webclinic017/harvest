# Builtins
import random
import unittest
import datetime as dt

import pandas as pd
from pandas.util.testing import assert_frame_equal

from harvest.utils import normalize_pands_dt_index
from harvest.storage.base import BaseStorage 


def gen_data(points: int=50):
    index = [dt.datetime.now() - dt.timedelta(minutes=1) * i for i in range(points)][::-1]
    df = pd.DataFrame(index=index, columns=['a', 'b', 'c'])
    df['a'] = [random.random() for _ in range(points)]
    df['b'] = [random.random() for _ in range(points)]
    df['c'] = [random.random() for _ in range(points)]
    df.index = normalize_pands_dt_index(df)

    return df

class TestBaseStorage(unittest.TestCase):
    def test_create_storage(self):
        storage = BaseStorage()

        self.assertEqual(storage.storage, {})

    def test_simple_store(self):
        storage = BaseStorage()
        data = gen_data(50)
        storage.store('A', '1MIN', data.copy(True))

        self.assertTrue(not pd.isna(data.iloc[0]['a']))
        self.assertEqual(list(storage.storage.keys()), ['A'])
        self.assertEqual(list(storage.storage['A'].keys()), ['1MIN'])

    def test_simple_load(self):
        storage = BaseStorage()
        data = gen_data(50)
        storage.store('A', '1MIN', data.copy(True))
        loaded_data = storage.load('A', '1MIN')

        assert_frame_equal(loaded_data, data)

    def test_store_no_overlap(self):
        storage = BaseStorage()
        data = gen_data(100)
        storage.store('A', '1MIN', data.copy(True).iloc[:50])
        storage.store('A', '1MIN', data.copy(True).iloc[50:])
        loaded_data = storage.load('A', '1MIN')

        self.assertTrue(not pd.isnull(data.iloc[0]['a']))
        self.assertTrue(not pd.isnull(loaded_data.iloc[0]['a']))
        assert_frame_equal(loaded_data, data)

    def test_store_overlap1(self):
        storage = BaseStorage()
        data = gen_data(100)
        storage.store('A', '1MIN', data.copy(True).iloc[:75])
        storage.store('A', '1MIN', data.copy(True).iloc[25:])
        loaded_data = storage.load('A', '1MIN')

        self.assertTrue(not pd.isnull(data.iloc[0]['a']))
        self.assertTrue(not pd.isnull(loaded_data.iloc[0]['a']))
        assert_frame_equal(loaded_data, data)

    def test_store_overlap2(self):
        storage = BaseStorage()
        data = gen_data(100)
        storage.store('A', '1MIN', data.copy(True).iloc[25:])
        storage.store('A', '1MIN', data.copy(True).iloc[:75])
        loaded_data = storage.load('A', '1MIN')

        self.assertTrue(not pd.isnull(data.iloc[0]['a']))
        self.assertTrue(not pd.isnull(loaded_data.iloc[0]['a']))
        assert_frame_equal(loaded_data, data)

    def test_store_within(self):
        storage = BaseStorage()
        data = gen_data(100)
        storage.store('A', '1MIN', data.copy(True).iloc[25:75])
        storage.store('A', '1MIN', data.copy(True))
        loaded_data = storage.load('A', '1MIN')

        self.assertTrue(not pd.isnull(data.iloc[0]['a']))
        self.assertTrue(not pd.isnull(loaded_data.iloc[0]['a']))
        assert_frame_equal(loaded_data, data)

    def test_store_over(self):
        storage = BaseStorage()
        data = gen_data(100)
        storage.store('A', '1MIN', data.copy(True))
        storage.store('A', '1MIN', data.copy(True).iloc[25:75])
        loaded_data = storage.load('A', '1MIN')

        self.assertTrue(not pd.isnull(data.iloc[0]['a']))
        self.assertTrue(not pd.isnull(loaded_data.iloc[0]['a']))
        assert_frame_equal(loaded_data, data)

    def test_load_no_interval(self):
        storage = BaseStorage()
        data = gen_data(50)
        storage.store('A', '1MIN', data.copy(True))
        loaded_data = storage.load('A')

        assert_frame_equal(loaded_data, data)



if __name__ == '__main__':
    unittest.main()