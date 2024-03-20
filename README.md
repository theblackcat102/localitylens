# Spotlight search for linux (WIP)

Search your linux machine like spotlight function in MacOS but better.


Ubuntu install:
```
sudo apt install libgirepository1.0-dev libcairo2 libcairo2-dev
```


```
import os
import json
import torch
import numpy as np
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModel
from localitylens import Pipeline

model_name = 'sentence-transformers/all-MiniLM-L6-v2'
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModel.from_pretrained(model_name)
model.eval()

def encode_data(sentence):
    # Tokenize sentences
    encoded_input = tokenizer([sentence], padding=True, truncation=True, return_tensors='pt')
    # for s2p(short query to long passage) retrieval task, add an instruction to query (not add instruction for passages)
    # encoded_input = tokenizer([instruction + q for q in queries], padding=True, truncation=True, return_tensors='pt')

    # Compute token embeddings
    with torch.no_grad():
        model_output = model(**encoded_input)
        # Perform pooling. In this case, cls pooling.
        sentence_embeddings = model_output[0][:, 0]
    return sentence_embeddings.numpy()

pipeline = Pipeline(f'bird_{model_postfix}.db', 'evidence', 384)
for question_id, sentence in enumerate(['Hello World', 'How are you']):
    row = {
            'sentence': sentence,
            'link': question_id
    }
    embedding = encode_data(sentence)[0]
    pipeline.insert(row, embedding, 'sentence', 'link')
query = 'Hi'
embedding = encode_data(query)[0]
result = pipeline.search(query, embedding, top_k=10)
print(result)
```