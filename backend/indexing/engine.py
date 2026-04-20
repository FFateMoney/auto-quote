from __future__ import annotations

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel, AutoModelForSequenceClassification
from backend.indexing.settings import get_settings


class Qwen3EmbeddingEngine:
    def __init__(self, model_id: str | None = None) -> None:
        settings = get_settings()
        self.model_path = model_id or settings.embedding_model_path
        self.reranker_path = settings.reranker_model_path
        
        print(f"[indexing] Loading Embedding model from: {self.model_path}")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, padding_side='left')
        # 使用 sdpa 代替 flash_attention_2，确保在未安装额外包的环境下也能运行
        self.model = AutoModel.from_pretrained(
            self.model_path, 
            torch_dtype=torch.bfloat16, 
            device_map="auto",
            trust_remote_code=True,
            attn_implementation="sdpa"
        )
        self.model.eval()

        self._reranker_model = None
        self._reranker_tokenizer = None

    def _ensure_reranker(self):
        if self._reranker_model is None:
            print(f"[indexing] Loading Reranker model from: {self.reranker_path}")
            self._reranker_tokenizer = AutoTokenizer.from_pretrained(self.reranker_path)
            self._reranker_model = AutoModelForSequenceClassification.from_pretrained(
                self.reranker_path,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
                num_labels=1,
                attn_implementation="sdpa"
            )
            self._reranker_model.eval()

    @torch.no_grad()
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # max_length 从 8192 降到 4096，减半显存占用
        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=4096,
            return_tensors="pt"
        ).to(self.model.device)

        outputs = self.model(**inputs)
        embeddings = self._last_token_pool(outputs.last_hidden_state, inputs['attention_mask'])
        embeddings = F.normalize(embeddings, p=2, dim=1)
        result = embeddings.cpu().to(torch.float32).tolist()

        # 立即清理所有中间变量
        del inputs, outputs, embeddings
        torch.cuda.empty_cache()

        return result

    @torch.no_grad()
    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """对候选文档进行精排打分"""
        if not documents:
            return []
        self._ensure_reranker()
        
        pairs = [[query, doc] for doc in documents]
        inputs = self._reranker_tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=4096,
            return_tensors="pt"
        ).to(self._reranker_model.device)
        
        scores = self._reranker_model(**inputs).logits.view(-1)
        # 归一化或直接返回原始 Logits (通常 Reranker 返回的是未归一化的分数)
        return scores.cpu().to(torch.float32).tolist()

    def _last_token_pool(self, last_hidden_states: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
        if left_padding:
            return last_hidden_states[:, -1]
        else:
            sequence_lengths = attention_mask.sum(dim=1) - 1
            batch_size = last_hidden_states.shape[0]
            return last_hidden_states[torch.arange(batch_size, device=last_hidden_states.device), sequence_lengths]
