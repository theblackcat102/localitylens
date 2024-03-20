"""
    Handle the indexing and search of raw texts
"""
try:
    import sqlite3
    conn = sqlite3.connect(':memory:')
    # If the following line does not raise an AttributeError, enable_load_extension is available
    conn.enable_load_extension(True)
    print("enable_load_extension is available.")
    conn.close()
except AttributeError:
    try:
        import sqlean as sqlite3
    except ImportError:
        raise ValueError("your sqlite3 doesn't support load_extension, fallback to sqlean failed\npip install sqlean")
finally:
    conn.close()
import simple_fts5
import sqlite_vss
from .utils import chunks
from node_parser.constants import DEFAULT_CHUNK_SIZE

class Pipeline():

    def __init__(self, db_name, prefix_name, embed_dim=384,
                 chunk_index=False,
                 chunk_size=10
                ):
        # Connect to SQLite database and enable extensions (adjust path as needed)
        self.conn = sqlite3.connect(db_name)
        self.conn.enable_load_extension(True)
        sqlite_vss.load(self.conn)  # Load sqlite-vss extension
        simple_fts5.load(self.conn) # load chinese tokenizer method
        self.main_table = prefix_name
        self.meta_table = prefix_name+'_metadata'
        self.faiss_table = prefix_name+'_faiss'
        self.bm25_table = prefix_name+'_fts5'
        self.embed_dim = embed_dim
        self.chunk_index = chunk_index
        self.chunk_size = chunk_size
        if chunk_index:
            self.chunk_table = prefix_name+'_chunk'
            from node_parser.text.utils import split_by_sentence_tokenizer
            self.splitter = split_by_sentence_tokenizer()
        self.init_schema()

    def init_schema(self, chunk_index=False):
        conn = self.conn
        # Create a virtual table for articles using sqlite-vss
        conn.execute(f'''
        CREATE TABLE IF NOT EXISTS {self.main_table} (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            link TEXT NOT NULL UNIQUE,
            content TEXT
        );''')
        conn.execute(f'''
        CREATE TABLE IF NOT EXISTS {self.meta_table} (
            metadata_id INTEGER PRIMARY KEY AUTOINCREMENT,
            row_id INTEGER NOT NULL,
            meta_key TEXT NOT NULL,
            meta_value TEXT,
            FOREIGN KEY (row_id) REFERENCES {self.main_table}(row_id)
        );''')

        conn.execute(f'''
        CREATE VIRTUAL TABLE IF NOT EXISTS {self.faiss_table} USING vss0(
            ctx_embedding({self.embed_dim})
        );
        ''')

        conn.execute(f'''
        CREATE VIRTUAL TABLE IF NOT EXISTS {self.bm25_table} USING fts5(
            content,
            content='{self.main_table}',
            content_rowid='row_id',
            tokenize="simple"
        );''')
        if not chunk_index:
            conn.execute(f'''
            CREATE TABLE IF NOT EXISTS {self.chunk_table} (
                chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                row_id INTEGER,
                paragraph TEXT
            );''')
            conn.execute(f'''
            CREATE INDEX IF NOT EXISTS idx_row_id ON {self.chunk_table}(row_id);
            ''')

            # Trigger to update FTS5 table on insert
            conn.execute(f'''
            CREATE TRIGGER IF NOT EXISTS insert_{self.bm25_table}_trg AFTER INSERT ON {self.main_table}
            BEGIN
                INSERT INTO {self.bm25_table}(rowid, content) VALUES (new.row_id, new.content);
            END;
            ''')

            # Trigger to update FTS5 table on update
            conn.execute(f'''
            CREATE TRIGGER IF NOT EXISTS update_{self.bm25_table}_trg AFTER UPDATE ON {self.main_table}
            BEGIN
                UPDATE {self.bm25_table} SET content = new.content WHERE rowid = old.row_id;
            END;
            ''')

        # Trigger to delete from FTS5 table on delete
        conn.execute(f'''
        CREATE TRIGGER IF NOT EXISTS del_{self.bm25_table}_trg AFTER DELETE ON {self.main_table}
        BEGIN
            DELETE FROM {self.bm25_table} WHERE rowid = old.row_id;
        END;
        ''')

    def insert(self, row, embedding, text_col, link_col, embedding_fn=None):
        cursor = self.conn.cursor()
        content = row[text_col]
        link = row[link_col]
        metadata_fields = set()
        for key in row.keys():
            if key not in (link_col, text_col):
                metadata_fields.add(key)
        _content = content
        if self.chunk_index:
            # truncate what's stored in the main table
            _content = content[:1024]
        cursor.execute(f'INSERT INTO {self.main_table} (link, content) VALUES (?, ?)', (link, _content))
        row_id = cursor.lastrowid
        # trigger fts5 insertion or manually if chunk_index
        if self.chunk_index:
            sentences = self.splitter(content)
            prev = ''
            for paragraph in chunks(sentences, self.chunk_size):
                _content = prev+'\n'.join([sent.strip() for sent in paragraph])
                if len(_content) <= DEFAULT_CHUNK_SIZE:
                    prev = _content
                    continue
                cursor.execute(f'INSERT INTO {self.chunk_table} (row_id, paragraph) VALUES (?, ?)', (row_id, _content))
                chunk_id = cursor.lastrowid
                cursor.execute(f'INSERT INTO {self.bm25_table} (rowid, content) VALUES (?, ?)', (chunk_id, _content))
                _embedding = embedding_fn(_content)
                cursor.execute(f'INSERT INTO {self.faiss_table} (rowid, ctx_embedding) VALUES (?, ?)', 
                            ( chunk_id, _embedding.tobytes() ))
                prev = ''
            if len(prev) > 0:
                _content = prev
                cursor.execute(f'INSERT INTO {self.chunk_table} (row_id, paragraph) VALUES (?, ?)', (row_id, _content))
                chunk_id = cursor.lastrowid
                cursor.execute(f'INSERT INTO {self.bm25_table} (rowid, content) VALUES (?, ?)', (chunk_id, _content))
                _embedding = embedding_fn(_content)
                cursor.execute(f'INSERT INTO {self.faiss_table} (rowid, ctx_embedding) VALUES (?, ?)', 
                            ( chunk_id, _embedding.tobytes() ))

        else:
            cursor.execute(f'INSERT INTO {self.faiss_table} (rowid, ctx_embedding) VALUES (?, ?)', 
                        ( row_id, embedding.tobytes() ))
        for key in metadata_fields:
            value = row[key]
            cursor.execute(f'SELECT metadata_id FROM {self.meta_table} WHERE row_id = ? AND meta_key = ?', (row_id, key))
            metadata = cursor.fetchone()
            if metadata is None:
                cursor.execute(f'INSERT INTO {self.meta_table} (row_id, meta_key, meta_value) VALUES (?, ?, ?)',
                            (row_id, key, value))
            else:
                cursor.execute(f'UPDATE {self.meta_table} SET meta_value = ? WHERE row_id = ? AND meta_key = ?',
                            (value, row_id, key))
        self.conn.commit()
        return row_id


    def search(self, query, embedding=None, top_k=30):
        row_ids = {}
        cursor = self.conn.cursor()
        cursor.execute(f'''
                SELECT rowid, bm25({self.bm25_table}) content
                  FROM {self.bm25_table}
                  WHERE content match simple_query(?)
              ORDER BY bm25({self.bm25_table}) 
                 LIMIT ?''', (query, top_k))
        res = cursor.fetchall()
        for rowid, bm25 in res:
            row_ids[rowid] = {'fts5':  bm25}

        if embedding is not None:
            sql = f'''SELECT
                        rowid,
                        distance
                    FROM {self.faiss_table}
                    WHERE vss_search({self.faiss_table}.ctx_embedding, vss_search_params(?, ?))
                '''
            res = self.conn.execute(sql, (embedding.tobytes(),top_k)).fetchall()
            for rowid, cosine in res:
                if rowid in row_ids:
                    row_ids[rowid]['faiss'] = cosine
                else:
                    row_ids[rowid] = {'faiss': cosine}
        result = []
        for rowid, data in row_ids.items():
            metadata = {}
            if self.chunk_index:
                cursor.execute(f'SELECT row_id, paragraph FROM {self.chunk_table} WHERE chunk_id = ?', (rowid, ))
                rowid, paragraph = cursor.fetchone()
                metadata['paragraph'] = paragraph
            cursor.execute(f'SELECT meta_key, meta_value FROM {self.meta_table} WHERE row_id = ?', (rowid, ))
            metadatas = cursor.fetchall()
            for key, value in metadatas:
                metadata[key] = value
            metadata['rowid'] = rowid
            metadata['_score'] = data
            res = cursor.execute(f'SELECT link from {self.main_table} where row_id = ?', (rowid, )).fetchone()
            metadata['link'] = res[0]
            result.append(metadata)
        return result

