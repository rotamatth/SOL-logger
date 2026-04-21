import os
import json
import pandas as pd
import pyterrier as pt
from pyterrier_t5 import MonoT5ReRanker
from pathlib import Path

pt.init()  # Initialize PyTerrier once before using indexing/retrieval features

# Current corpus and index location used by the search engine
CORPUS = 'datasets/commonlit/docs.jsonl'
IDX_PATH = Path.cwd() / "index" / "commonlit"

def read_corpus():
    # Read the JSONL corpus file and load it into a pandas DataFrame
    lines = []
    with open(str(CORPUS)) as f:
        lines = f.read().splitlines()

    line_dicts = [json.loads(line) for line in lines]
    df_final = pd.DataFrame(line_dicts)

    # Remove duplicate rows to avoid indexing the same document twice
    df_final.drop_duplicates(inplace=True,ignore_index=True)
    return df_final

class Ranker(object):

    def __init__(self, wmodel):
        # Index handle; loaded or created later
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

        # Build an indexer describing which fields are stored as metadata
        # and which field is actually indexed for retrieval
        ### commonlit
        indexer = pt.IterDictIndexer(
            index_path = str(IDX_PATH),
            overwrite=True,
            meta={ # metadata recorded in index
                "docno": max([len(docno) for docno in df_final["docno"]]),
                "title": max([len(title) for title in df_final["title"]]),
                "snippet": max([len(snippet) for snippet in df_final["snippet"]]),
                "author": max([len(author) for author in df_final["author"]]),
                "url": max([len(url) for url in df_final["url"]]),
                "source": max([len(source) for source in df_final["source"]])
            },
            text_attrs = ["snippet"], # only the snippet text is indexed for search
            stemmer="porter",
            stopwords="terrier",
        )

        ## indexing corpus
        # Create the on-disk PyTerrier index and keep a handle to it
        self.idx = indexer.index(df_iter())

    def rank_publications(self, query, page, rpp):

        itemlist = []

        if query is not None:
            # Lazily load the index from disk if it is not already in memory
            if self.idx is None:
                try:
                    self.idx = pt.IndexFactory.of(os.path.join(IDX_PATH, 'data.properties'))
                except Exception as e:
                    print('No index available: ', e)

            if self.idx is not None:
                index_ref = self.idx

                firstStageRetriever = pt.BatchRetrieve(
                    index_ref,
                    controls={"wmodel": self.firstRanker}
                )
                full_retriever_pipeline = (
                    firstStageRetriever
                    >> pt.text.get_text(index_ref, "snippet")
                    >> self.reranker
                )

<<<<<<< HEAD
                items = full_retriever_pipeline.search(query)['docno'][page*rpp:(page+1)*rpp].tolist()
                itemlist = []

                for i in items:
                    item = self.dataset.loc[self.dataset["docno"] == i]
                    itemlist.append(
=======
                firstStageRetriever = pt.BatchRetrieve(self.idx, controls={"wmodel": self.firstRanker})
                # full_retriever_pipeline = firstStageRetriever >> pt.text.get_text(self.idx, "snippet") >> self.reranker
                full_retriever_pipeline = firstStageRetriever
                items = full_retriever_pipeline.search(query)['docno'][page*rpp:(page+1)*rpp].tolist()
                itemlist = []  

                ### commonlit
                for i in items: 
                    item =  self.dataset.loc[self.dataset["docno"]==i]
                    itemlist.append(                                            # Adjust to the data fields that the collection you want to use provides (Corresponding don't have to be adjusted)
>>>>>>> upstream/main
                        {
                            'title': item["title"].values[0],
                            'snippet': item["snippet"].values[0],
                            'source_title': item["source"].values[0],
                            'docid': item["docno"].values[0],
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