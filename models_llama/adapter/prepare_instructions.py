from __future__ import annotations

import json
import os
import random
from typing import Any
from typing import List

import torch
from loguru import logger
from pydantic import BaseModel
from sentencepiece import SentencePieceProcessor
from tqdm import tqdm

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# TODO figure out the context window of llama and if it can change after fine tuning
import gzip


def json_dump(filename, obj, gz=False):
    if gz:
        open_file = gzip.open
        assert filename.endswith(".gz")
        with open_file(filename, 'wt', encoding="UTF-8") as f:
            json.dump(obj, f)
    else:
        open_file = open
        with open_file(filename, 'w', encoding="UTF-8") as f:
            json.dump(obj, f)


def json_load(filename):
    if filename.endswith(".gz"):
        open_file = gzip.open
        with open_file(filename, 'rt', encoding="UTF-8") as f:
            return json.load(f)
    else:
        open_file = open
        with open_file(filename, 'r', encoding="UTF-8") as f:
            return json.load(f)


class Tokenizer:
    """
    # Copyright (c) Meta Platforms, Inc. and affiliates.
    # This software may be used and distributed according to the terms of the GNU General Public License version 3.
    """

    def __init__(self, model_path: str = "7B_tokenizer/tokenizer.model"):
        # reload tokenizer
        assert os.path.isfile(model_path), model_path
        self.sp_model = SentencePieceProcessor(model_file=model_path)
        logger.info(f"Reloaded SentencePiece model from {model_path}")

        # BOS / EOS token IDs
        self.n_words: int = self.sp_model.vocab_size()
        self.bos_id: int = self.sp_model.bos_id()
        self.eos_id: int = self.sp_model.eos_id()
        self.pad_id: int = self.sp_model.pad_id()
        logger.info(f"#words: {self.n_words} - BOS ID: {self.bos_id} - EOS ID: {self.eos_id}")
        assert self.sp_model.vocab_size() == self.sp_model.get_piece_size()

    def encode(self, s: str, bos: bool, eos: bool) -> List[int]:
        assert type(s) is str
        t = self.sp_model.encode(s)
        if bos:
            t = [self.bos_id] + t
        if eos:
            t = t + [self.eos_id]
        return t

    def decode(self, t: List[int]) -> str:
        return self.sp_model.decode(t)


class InstructionDataset(BaseModel):
    reactions_file: str = f"{THIS_DIR}/../../ord_data/data_from_pb_no_warning_20230416_dedup.json"

    ord_procedure_field: str = "notes__procedureDetails"

    ord_target_fields: list[str] = ["inputs", ]

    prompt_template: str = "### Procedure:\n{instruction}\n\n### ORD-JSON:\n"

    tokenizer_path: str = f"{THIS_DIR}/7B_tokenizer/tokenizer.model"

    max_token: int = 900  # fits 24 gb gpu

    train_size: float = 10000

    test_size: float = 2000

    n_all_alpaca_dicts: int = 0

    n_accepted_alpaca_dicts: int = 0

    seed: int = 42

    train_data: list[dict] = []

    test_data: list[dict] = []

    @property
    def actual_train_size(self):
        if isinstance(self.train_size, int) and self.train_size > 1:
            return self.train_size
        elif isinstance(self.train_size, float) and 0 < self.train_size < 1:
            return int(self.n_accepted_alpaca_dicts * self.train_size)
        raise ValueError(f"weird train_size: {self.train_size}")

    @property
    def actual_test_size(self):
        if isinstance(self.test_size, int) and self.test_size > 1:
            return self.test_size
        elif isinstance(self.test_size, float) and 0 < self.test_size < 1:
            return self.n_accepted_alpaca_dicts - self.actual_train_size
        raise ValueError(f"weird test_size: {self.test_size}")

    def collect_reactions(self) -> list[dict]:
        with open(self.reactions_file, "r") as f:
            reactions = json.load(f)
        return reactions

    def reaction_dict_to_alpaca_dict(self, r: dict[str, Any]):
        output = {k: r[k] for k in self.ord_target_fields}
        # TODO this should be done in extracting from postgres...
        if 'conditions' in self.ord_target_fields:
            output['conditions'].pop('details', None)
        if 'workups' in self.ord_target_fields:
            for w in output['workups']:
                w.pop('details')
        if 'outcomes' in self.ord_target_fields:
            for reaction_outcome in output['outcomes']:
                if 'analyses' not in reaction_outcome:
                    continue
                for analysis in reaction_outcome['analyses'].values():
                    analysis.pop('details')
        d = {
            "reaction_id": r['reaction_id'],
            "instruction": r[self.ord_procedure_field],
            "output": json.dumps(output),
        }

        for v in d.values():
            assert isinstance(v, str)
        return d

    @staticmethod
    def get_n_tokens(example: str, tokenizer: Tokenizer):
        example = torch.tensor(tokenizer.encode(example, bos=True, eos=True), dtype=torch.int64)
        return example.shape[0]

    def save(self):
        if len(self.train_data) == 0:
            self.load()
        filename = f"OrdAlpaca_MaxToken{self.max_token}_TrainSize{self.actual_train_size}_TestSize{self.actual_test_size}_{'-'.join(self.ord_target_fields)}.json.gz"
        ds = self.dict()
        json_dump(filename, ds, gz=True)

    def load(self, plot_token_ecdf=False):
        tmp_filename = f"prepare_instructions_alpaca_dicts_tokenized_{'-'.join(self.ord_target_fields)}.json.gz"
        try:
            all_alpaca_dicts = json_load(tmp_filename)
        except (FileNotFoundError, ValueError) as e:
            tokenizer = Tokenizer(model_path=self.tokenizer_path)
            all_reactions = self.collect_reactions()
            len_chars = []
            len_tokens = []
            all_alpaca_dicts = []
            for r in tqdm(all_reactions):
                d = self.reaction_dict_to_alpaca_dict(r)
                all_alpaca_dicts.append(d)
                example = self.prompt_template.format_map({"instruction": d['instruction']}) + d['output']
                n_token = self.get_n_tokens(example, tokenizer)
                d['n_token_example'] = n_token
                len_chars.append(len(example))
                len_tokens.append(n_token)
            json_dump(tmp_filename, all_alpaca_dicts, gz=True)

        self.n_all_alpaca_dicts = len(all_alpaca_dicts)

        if plot_token_ecdf:
            self.plot_ecdf_n_token_example(all_alpaca_dicts=all_alpaca_dicts)

        accepted_alpaca_dicts = []
        for d in all_alpaca_dicts:
            n_token = d['n_token_example']
            if n_token <= self.max_token:
                accepted_alpaca_dicts.append(d)
        self.n_accepted_alpaca_dicts = len(accepted_alpaca_dicts)
        logger.info(f"# of all alpaca dicts: {len(all_alpaca_dicts)}")
        logger.info(
            f"# of accepted alpaca dicts: {len(accepted_alpaca_dicts)} ({round(len(accepted_alpaca_dicts) / len(all_alpaca_dicts), 4) * 100}%)")

        random.seed(self.seed)
        accepted_alpaca_dicts = random.sample(accepted_alpaca_dicts, self.actual_train_size + self.actual_test_size)
        random.shuffle(accepted_alpaca_dicts)
        train, test = accepted_alpaca_dicts[:self.actual_train_size], accepted_alpaca_dicts[self.actual_train_size:]
        self.train_data = train
        self.test_data = test

    def plot_ecdf_n_token_example(self, all_alpaca_dicts):
        assert len(self.train_data) > 0
        import plotly.express as px
        import plotly
        fig = px.ecdf(
            x=[d['n_token_example'] for d in all_alpaca_dicts],
            marginal="histogram",
            labels={
                "x": "n_token(prompt + response)",
            }
        )
        plotly.offline.plot(fig, filename=f'ecdf_n_token_{"-".join(self.ord_target_fields)}.html')


if __name__ == '__main__':
    dataset = InstructionDataset(
        ord_target_fields=[
            'inputs',
            'conditions',
            'outcomes',
            'workups',
        ],
        train_size=0.8,
        test_size=0.2,
    )
    dataset.save()
