import os
import pyterrier as pt
# from pyterrier_t5 import MonoT5ReRanker
import pandas as pd
from pathlib import Path
pt.init()

import ir_datasets
import json

# DATASET = 'irds:argsme/2020-04-01/touche-2020-task-1'
# IDX_PATH = './index/argsme'

# CORPUS = r'datasets/kid-friend-en/docs.jsonl'
# IDX_PATH = Path.cwd() / "index" / "kid-friend-en"

CORPUS = r'datasets/commonlit/docs.jsonl'
IDX_PATH = Path.cwd() / "index" / "commonlit"

def read_corpus():
    lines = []
    with open(str(CORPUS)) as f:
        lines = f.read().splitlines()

    line_dicts = [json.loads(line) for line in lines]
    df_final = pd.DataFrame(line_dicts)
    df_final.drop_duplicates(inplace=True,ignore_index=True)
    return df_final


class Ranker(object):

    def __init__(self, wmodel):
        self.idx = None
        self.firstRanker = 'BM25'
        # self.reranker = MonoT5ReRanker(text_field='snippet', model = 'castorini/monot5-base-msmarco')
        self.dataset = read_corpus()

    def index(self):

        ## reading corpus
        df_final = read_corpus()
        self.dataset = df_final

        ### commonlit
        def df_iter():
            for i, row in df_final.iterrows():
                yield {
                    "docno": row["docno"],
                    "title": row["title"],
                    "snippet": row["snippet"],
                    "author": row["author"],
                    "url": row["url"],
                    "source": row["source"]
                }

        ### commonlit
        indexer = pt.IterDictIndexer(
            index_path = str(IDX_PATH),
            meta={ # metadata recorded in index
                "docno": max([len(docno) for docno in df_final["docno"]]),
                "title": max([len(title) for title in df_final["title"]]),
                "snippet": max([len(snippet) for snippet in df_final["snippet"]]),
                "author": max([len(author) for author in df_final["author"]]),
                "url": max([len(url) for url in df_final["url"]]),
                "source": max([len(source) for source in df_final["source"]])
            },
            text_attrs = ["snippet"], # columns indexed
            stemmer="porter",
            stopwords="terrier",
        )

        ## indexing corpus
        self.idx = indexer.index(df_iter())

    def rank_publications(self, query, page, rpp):

        itemlist = []
        import os
       
        idx_path_abs = os.path.abspath(os.path.join(IDX_PATH, 'data.properties'))
    
        if query is not None:
            if self.idx is None:
                try:
                    self.idx = pt.IndexFactory.of(os.path.join(IDX_PATH, 'data.properties'))
                except Exception as e:
                    print('No index available: ', e)
            if self.idx is not None:

                meta_index = self.idx.getMetaIndex()

                firstStageRetriever = pt.BatchRetrieve(self.idx, controls={"wmodel": self.firstRanker})
                # full_retriever_pipeline = firstStageRetriever >> pt.text.get_text(self.idx, "snippet") >> self.reranker
                full_retriever_pipeline = firstStageRetriever
                items = full_retriever_pipeline.search(query)['docno'][page*rpp:(page+1)*rpp].tolist()
                itemlist = []  

                ### commonlit
                for i in items:
                    item =  self.dataset.loc[self.dataset["docno"]==i]
                    if item.empty:
                        continue  # skip documents not found in metadata
                    itemlist.append(                                            # Adjust to the data fields that the collection you want to use provides (Corresponding don't have to be adjusted)
                        {
                            'title': item["title"].values[0],
                            'snippet': item["snippet"].values[0],
                            'source_title' : item["source"].values[0],
                            'docid' : item["docno"].values[0],
                            'link': item["url"].values[0],
                        }
                    )                    
                   
        return {
            'page': page,
            'rpp': rpp,
            'query': query,
            'itemlist': itemlist,
            'num_found': len(itemlist)
        }
