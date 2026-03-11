from datetime import datetime 
import requests
import pandas as pd
import json
from tqdm.notebook import tqdm

f = open("API_keys.json")
data = json.load(f)

API_KEY = data["google"]["api_key"]
SEARCH_ENGINE_ID = data["google"]["search_engine_id"]
SERP_endpoint = data["google"]["SERP_endpoint"]
f.close()

def get_google_SERP(query):

    payload = {
            'key': API_KEY,
            'q': query,
            'cx': SEARCH_ENGINE_ID,
            'lr': "lang_en"
        }
    
    try:
        SERP_response = requests.get(url=SERP_endpoint, params=payload)
    except requests.ConnectionError:
        return "Connection Error"
    
    search_results = SERP_response.json()

    return search_results
    
    for result in SERP_result_set["items"]:
        try:
            web_title =  result["title"]
        except:
            web_title = None
        try:
            web_url = result["link"]
        except:
            web_url = None
        try:
            web_snippet = result["snippet"]
        except:
            web_snippet = None

def get_google_results(queries_df, results_file_name):

    SERP_results = []
    today = datetime.now()
    today = today.strftime("%Y_%m_%d")

    for _, row in tqdm(queries_df.iterrows(), total=len(queries_df)):
        query = row["query"] 
        query_category = str(row["ngram"]) + '-gram'

        payload = {
            'key': API_KEY,
            'q': query,
            'cx': SEARCH_ENGINE_ID,
            'lr': "lang_en"
        }

        SERP_response = requests.get(url=SERP_endpoint, params=payload)
        try:
            SERP_result_set = SERP_response.json()
            asked_query = payload['q']
            for result in SERP_result_set["items"]:
                try:
                    web_title =  result["title"]
                except:
                    web_title = None
                try:
                    web_url = result["link"]
                except:
                    web_url = None
                try:
                    web_snippet = result["snippet"]
                except:
                    web_snippet = None

                # try:
                #     req = Request(
                #         url= web_url, 
                #         headers={'User-Agent': 'Mozilla/5.0'}
                #     )
                #     html = urlopen(req).read().decode('utf-8')
                #     # html = urllib.request.urlopen(web_url).read().decode('utf-8')
                #     # web_text = get_text(html) 
                # except Exception as error:
                #     # print(error)
                #     # print(web_url)
                #     web_text = None
                
                SERP_results.append([query, asked_query, query_category, web_title, web_url, web_snippet, today])
        except:
            print(query)
            SERP_results.append([query, asked_query, query_category, None, None, None, today])

    SERP_df = pd.DataFrame(SERP_results, columns=["query", "asked_query", "query_category", "web_title", "web_url", "web_snippet", "date_crawled"])
    SERP_df.to_excel("../data/" + results_file_name + ".xlsx", index=False)