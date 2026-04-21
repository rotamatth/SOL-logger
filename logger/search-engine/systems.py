from operator import index
import os
import pyterrier as pt
from pyterrier_t5 import MonoT5ReRanker
import pandas as pd
from pathlib import Path
pt.init()  # Initialize PyTerrier once before using indexing/retrieval features

import ir_datasets
import json

# Alternative dataset configuration kept for previous experiments
# DATASET = 'irds:argsme/2020-04-01/touche-2020-task-1'
# IDX_PATH = './index/argsme'

# Alternative local corpus configuration
# CORPUS = r'datasets/kid-friend-en/docs.jsonl'
# IDX_PATH = Path.cwd() / "index" / "kid-friend-en"

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
        # self.wmodel = wmodel
        self.firstRanker = 'BM25'
        # self.reranker = MonoT5ReRanker()
        self.reranker = MonoT5ReRanker(text_field='snippet', model = 'castorini/monot5-base-msmarco')
        self.dataset = read_corpus()

        # Old ir_datasets-based setup kept for reference
        # self.dataset = ir_datasets.load("argsme/2020-04-01/touche-2020-task-1")
        # self.docstore = self.dataset.docs_store()

    def index(self):
        
        # Old indexing logic for ir_datasets kept for reference
        # dataset = pt.get_dataset(DATASET)

        # title_dict = {}
        # with open("index/titles.json") as f:
        #     for line in f:
        #         l = json.loads(line)
        #         key, value = next(iter(l.items()))
        #         title_dict[key] = value

        # def filter_dataset():
        #     seen = set()
        #     for i, doc in enumerate(dataset.get_corpus_iter()):
        #         doc_id = doc['docno']
        #         if doc_id not in seen:
        #             seen.add(doc_id)
        #             if len(doc['premises_texts']) > 100 and len(doc['premises_texts']) < 3000:
        #                 title = title_dict.get(doc_id)
        #                 if not title:
        #                     continue
        #                 doc['title'] = title
        #                 yield doc

        # indexer = pt.IterDictIndexer(IDX_PATH, meta={'docno': 39, 'title':256}, fields=['title', 'conclusion', 'premises_texts', 'aspects_names', 'source_id', 'source_title', 'topic', 'source_url', 'date', 'author_image_url'],text_attrs=['premises_texts'])
        # self.idx = indexer.index(filter_dataset())

        ## reading corpus
        # Reload corpus from disk before indexing
        df_final = read_corpus()
        self.dataset = df_final

        ## creating corpus iterator
        ### kid-friend-en
        # Old iterator for a different dataset schema
        # def df_iter():
        #     for i, row in df_final.iterrows():
        #         yield {
        #             "docno": row["docno"],
        #             "title": row["title"],
        #             "snippet": row["snippet"],
        #             "text": row["main_content"]
        #         }

        ### commonlit
        # Convert each DataFrame row into the dictionary format expected by PyTerrier
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

        ## creating indexer
        ### kid-friend-en
        # Old indexer for another corpus schema
        # indexer = pt.IterDictIndexer(
        #     index_path = str(IDX_PATH),
        #     meta={ # metadata recorded in index
        #         "docno": max([len(docno) for docno in df_final["docno"]]),
        #         "title": max([len(title) for title in df_final["title"]]),
        #         "snippet": max([len(snippet) for snippet in df_final["snippet"]]),
        #         "text": max([len(main_content) for main_content in df_final["main_content"]])
        #     },
        #     text_attrs = ["text"], # columns indexed
        #     stemmer="porter",
        #     stopwords="terrier",
        # )

        ### commonlit
        # Build an indexer describing which fields are stored as metadata
        # and which field is actually indexed for retrieval
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

        # List of result dictionaries returned to the Flask API
        itemlist = []
        import os
       
        # Absolute path to the existing PyTerrier index metadata file
        idx_path_abs = os.path.abspath(os.path.join(IDX_PATH, 'data.properties'))
    
        if query is not None:
            # Lazily load the index from disk if it is not already in memory
            if self.idx is None:
                try:
                    self.idx = pt.IndexFactory.of(os.path.join(IDX_PATH, 'data.properties'))
                except Exception as e:
                    print('No index available: ', e)

            if self.idx is not None:

                # Access stored metadata fields for indexed documents
                index = pt.IndexFactory.of(self.idx)
                meta_index = index.getMetaIndex()

                firstStageRetriever = pt.BatchRetrieve(self.idx, controls={"wmodel": self.firstRanker})
                full_retriever_pipeline = firstStageRetriever >> pt.text.get_text(self.idx, "snippet") >> self.reranker
                items = full_retriever_pipeline.search(query)['docno'][page*rpp:(page+1)*rpp].tolist()
                itemlist = []

                # Old result-construction logic for other datasets kept for reference
                # for i in items: 
                #     item =  self.docstore.get(i)
                #     internal_id = meta_index.getDocument("docno", i)
                #     itemlist.append(                                            # Adjust to the data fields that the collection you want to use provides (Corresponding don't have to be adjusted)
                #         {
                #             'title': meta_index.getItem('title', internal_id),
                #             'snippet': item.premises_texts,
                #             'source_title' : item.source_title,
                #             'date': item.date,
                #             'docid' : item.doc_id,
                #             'link': item.source_url,
                #             'thumbnail': item.author_image_url
                #         }
                #     )

                ### kid-friend-en
                # Old result mapping for another corpus schema
                # for i in items: 
                #     item =  self.dataset.loc[self.dataset["docno"]==i]
                #     itemlist.append(                                            # Adjust to the data fields that the collection you want to use provides (Corresponding don't have to be adjusted)
                #         {
                #             'title': item["title"].values[0],
                #             'snippet': item["snippet"].values[0],
                #             'source_title' : item["title"].values[0],
                #             'docid' : item["docno"].values[0]
                #         }
                #     )     

                ### commonlit
                # Rebuild the API response using metadata stored in the original DataFrame
                for i in items: 
                    item =  self.dataset.loc[self.dataset["docno"]==i]
                    itemlist.append(                                            # Adjust to the data fields that the collection you want to use provides (Corresponding don't have to be adjusted)
                        {
                            'title': item["title"].values[0],
                            'snippet': item["snippet"].values[0],
                            'source_title' : item["source"].values[0],
                            'docid' : item["docno"].values[0],
                            'link': item["url"].values[0],
                        }
                    )                    
                   
        # Return ranking results in the JSON structure expected by the Flask API
        return {
            'page': page,
            'rpp': rpp,
            'query': query,
            'itemlist': itemlist,
            'num_found': len(itemlist)
        }