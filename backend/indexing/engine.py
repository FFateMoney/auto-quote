from __future__ import annotations

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel, AutoModelForCausalLM
from backend.indexing.settings import get_settings


class Qwen3EmbeddingEngine:
    _DEFAULT_RERANK_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"

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
        self._reranker_true_token_id: int | None = None
        self._reranker_false_token_id: int | None = None
        self._reranker_prefix_tokens: list[int] = []
        self._reranker_suffix_tokens: list[int] = []
        self._reranker_max_length = 4096

    def _ensure_reranker(self):
        if self._reranker_model is None:
            print(f"[indexing] Loading Reranker model from: {self.reranker_path}")
            self._reranker_tokenizer = AutoTokenizer.from_pretrained(self.reranker_path, padding_side="left")
            self._reranker_model = AutoModelForCausalLM.from_pretrained(
                self.reranker_path,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True,
                attn_implementation="sdpa"
            )
            self._reranker_model.eval()
            self._reranker_false_token_id = self._reranker_tokenizer.convert_tokens_to_ids("no")
            self._reranker_true_token_id = self._reranker_tokenizer.convert_tokens_to_ids("yes")
            if self._reranker_false_token_id is None or self._reranker_true_token_id is None:
                raise RuntimeError("reranker_token_ids_not_found_for_yes_no")
            prefix = (
                "<|im_start|>system\n"
                'Judge whether the Document meets the requirements based on the Query and the Instruct provided. '
                'Note that the answer can only be "yes" or "no".'
                "<|im_end|>\n<|im_start|>user\n"
            )
            suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
            self._reranker_prefix_tokens = self._reranker_tokenizer.encode(prefix, add_special_tokens=False)
            self._reranker_suffix_tokens = self._reranker_tokenizer.encode(suffix, add_special_tokens=False)

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

        pairs = [
            self._format_reranker_input(self._DEFAULT_RERANK_INSTRUCTION, query, doc)
            for doc in documents
        ]
        inputs = self._process_reranker_inputs(pairs)
        logits = self._reranker_model(**inputs).logits[:, -1, :]
        true_vector = logits[:, self._reranker_true_token_id]
        false_vector = logits[:, self._reranker_false_token_id]
        pair_scores = torch.stack([false_vector, true_vector], dim=1)
        pair_scores = torch.nn.functional.log_softmax(pair_scores, dim=1)
        return pair_scores[:, 1].exp().cpu().to(torch.float32).tolist()

    def _last_token_pool(self, last_hidden_states: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
        if left_padding:
            return last_hidden_states[:, -1]
        else:
            sequence_lengths = attention_mask.sum(dim=1) - 1
            batch_size = last_hidden_states.shape[0]
            return last_hidden_states[torch.arange(batch_size, device=last_hidden_states.device), sequence_lengths]

    def _format_reranker_input(self, instruction: str | None, query: str, doc: str) -> str:
        active_instruction = instruction or self._DEFAULT_RERANK_INSTRUCTION
        return f"<Instruct>: {active_instruction}\n<Query>: {query}\n<Document>: {doc}"

    def _process_reranker_inputs(self, pairs: list[str]) -> dict[str, torch.Tensor]:
        max_length = max(1, self._reranker_max_length - len(self._reranker_prefix_tokens) - len(self._reranker_suffix_tokens))
        inputs = self._reranker_tokenizer(
            pairs,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=max_length,
        )
        for index, token_ids in enumerate(inputs["input_ids"]):
            inputs["input_ids"][index] = self._reranker_prefix_tokens + token_ids + self._reranker_suffix_tokens
        padded = self._reranker_tokenizer.pad(inputs, padding=True, return_tensors="pt", max_length=self._reranker_max_length)
        target_device = self._model_input_device(self._reranker_model)
        return {key: value.to(target_device) for key, value in padded.items()}

    def _model_input_device(self, model) -> torch.device:
        device_map = getattr(model, "hf_device_map", None)
        if isinstance(device_map, dict):
            for location in device_map.values():
                if location in ("disk", "meta"):
                    continue
                if isinstance(location, int):
                    return torch.device(f"cuda:{location}")
                return torch.device(str(location))
        model_device = getattr(model, "device", None)
        if model_device is not None and getattr(model_device, "type", None) != "meta":
            return model_device
        try:
            first_param = next(model.parameters())
        except StopIteration:
            return torch.device("cpu")
        return first_param.device if getattr(first_param.device, "type", None) != "meta" else torch.device("cpu")
