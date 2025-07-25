import argparse
import logging
import math
import os
import random
import json

import datasets
import evaluate 
import nltk
import numpy as np
import torch
from datasets import load_dataset
from torch.utils.data.dataloader import DataLoader
from tqdm.auto import tqdm

import transformers
from accelerate import Accelerator
from filelock import FileLock
from transformers import (
    CONFIG_MAPPING,
    MODEL_MAPPING,
    AdamW,
    AutoConfig,
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    SchedulerType,
    get_scheduler,
    set_seed,
)

from utils.text_normalization import normalize_answer
from dotenv import load_dotenv

# Load pre-defined environment variable
load_dotenv()

logger = logging.getLogger(__name__)

if os.getenv('WANDB_API_KEY') is None:
    USE_WANDB = False
else:
    USE_WANDB = True
    wandb_key = os.getenv('WANDB_API_KEY')

# You should update this to your particular problem to have better documentation of `model_type`
MODEL_CONFIG_CLASSES = list(MODEL_MAPPING.keys())
MODEL_TYPES = tuple(conf.model_type for conf in MODEL_CONFIG_CLASSES)

def parse_args():
    parser = argparse.ArgumentParser(description="Finetune a transformers model on a text classification task")
    parser.add_argument(
        "--dataset_name",
        type=str,
        default=None,
        help="The name of the dataset to use (via the datasets library).",
    )
    parser.add_argument(
        "--dataset_config_name",
        type=str,
        default=None,
        help="The configuration name of the dataset to use (via the datasets library).",
    )
    parser.add_argument(
        "--train_file", type=str, default=None, help="A csv or a json file containing the training data."
    )
    parser.add_argument(
        "--validation_file", type=str, default=None, help="A csv or a json file containing the validation data."
    )
    parser.add_argument(
        "--test_file", type=str, default=None, help="A csv or a json file containing the test data."
    )
    parser.add_argument(
        "--max_source_length",
        type=int,
        default=1024,
        help="The maximum total input sequence length after "
        "tokenization.Sequences longer than this will be truncated, sequences shorter will be padded.",
    )
    parser.add_argument(
        "--source_prefix",
        type=str,
        default=None,
        help="A prefix to add before every source text " "(useful for T5 models).",
    )
    parser.add_argument(
        "--preprocessing_num_workers",
        type=int,
        default=None,
        help="The number of processes to use for the preprocessing.",
    )
    parser.add_argument(
        "--max_target_length",
        type=int,
        default=64,
        help="The maximum total sequence length for target text after "
        "tokenization. Sequences longer than this will be truncated, sequences shorter will be padded."
        "during ``evaluate`` and ``predict``.",
    )
    parser.add_argument(
        "--val_max_target_length",
        type=int,
        default=None,
        help="The maximum total sequence length for validation "
        "target text after tokenization.Sequences longer than this will be truncated, sequences shorter will be "
        "padded. Will default to `max_target_length`.This argument is also used to override the ``max_length`` "
        "param of ``model.generate``, which is used during ``evaluate`` and ``predict``.",
    )
    parser.add_argument(
        "--num_beams",
        type=int,
        default=None,
        help="Number of beams to use for evaluation. This argument will be "
        "passed to ``model.generate``, which is used during ``evaluate`` and ``predict``.",
    )
    parser.add_argument(
        "--model_name_or_path",
        type=str,
        help="Path to pretrained model or model identifier from huggingface.co/models.",
        required=True,
    )
    parser.add_argument(
        "--config_name",
        type=str,
        default=None,
        help="Pretrained config name or path if not the same as model_name",
    )
    parser.add_argument(
        "--tokenizer_name",
        type=str,
        default=None,
        help="Pretrained tokenizer name or path if not the same as model_name",
    )
    parser.add_argument(
        "--text_column",
        type=str,
        default=None,
        help="The name of the column in the datasets containing the full texts (for summarization).",
    )
    parser.add_argument(
        "--summary_column",
        type=str,
        default=None,
        help="The name of the column in the datasets containing the summaries (for summarization).",
    )
    parser.add_argument(
        "--use_slow_tokenizer",
        action="store_true",
        help="If passed, will use a slow tokenizer (not backed by the 🤗 Tokenizers library).",
    )
    parser.add_argument(
        "--per_device_train_batch_size",
        type=int,
        default=8,
        help="Batch size (per device) for the training dataloader.",
    )
    parser.add_argument(
        "--per_device_eval_batch_size",
        type=int,
        default=8,
        help="Batch size (per device) for the evaluation dataloader.",
    )
    parser.add_argument(
        "--learning_rate",
        type=float,
        default=5e-5,
        help="Initial learning rate (after the potential warmup period) to use.",
    )
    parser.add_argument("--weight_decay", type=float, default=0.0, help="Weight decay to use.")
    parser.add_argument("--num_train_epochs", type=int, default=3, help="Total number of training epochs to perform.")
    parser.add_argument(
        "--max_train_steps",
        type=int,
        default=None,
        help="Total number of training steps to perform. If provided, overrides num_train_epochs.",
    )
    parser.add_argument(
        "--gradient_accumulation_steps",
        type=int,
        default=1,
        help="Number of updates steps to accumulate before performing a backward/update pass.",
    )
    parser.add_argument(
        "--lr_scheduler_type",
        type=SchedulerType,
        default="linear",
        help="The scheduler type to use.",
        choices=["linear", "cosine", "cosine_with_restarts", "polynomial", "constant", "constant_with_warmup"],
    )
    parser.add_argument(
        "--num_warmup_steps", type=int, default=0, help="Number of steps for the warmup in the lr scheduler."
    )
    parser.add_argument("--output_dir", type=str, default=None, help="Where to store the final model.")
    parser.add_argument("--seed", type=int, default=None, help="A seed for reproducible training.")
    parser.add_argument(
        "--model_type",
        type=str,
        default=None,
        help="Model type to use if training from scratch.",
        choices=MODEL_TYPES,
    )
    parser.add_argument(
        "--overwrite_cache", type=bool, default=False, help="Overwrite the cached training and evaluation sets"
    )
    parser.add_argument(
        "--max_length", type=int, default=128, help="max length"
    )
    parser.add_argument(
        "--pad_to_max_length", type=bool, default=True, help="do pading"
    )
    parser.add_argument(
        "--ignore_pad_token_for_loss", type=bool, default=True, help="do pading"
    )
    parser.add_argument(
        "--logging_steps", type=int, default=500, help="do pading"
    )
    parser.add_argument(
        "--save_steps", type=int, default=5000, help="do pading"
    )
    parser.add_argument(
        "--save_every_checkpoint", action="store_true"
    )
    parser.add_argument(
        "--max_grad_norm", type=float, default=1.0, help="max_grad_norm"
    )
    parser.add_argument(
        "--no_kb", action="store_true"
    )
    parser.add_argument(
        "--exp_name",
        type=str,
        help="Description to the experiment",
        default='exp',
    )
    parser.add_argument(
        "--wandb_exp_name",
        type=str,
        default='DialoGLM',
        help="Description to the experiment worksheet name",
    )

    args = parser.parse_args()

    # Sanity checks
    if args.dataset_name is None and args.train_file is None and args.validation_file is None:
        raise ValueError("Need either a dataset name or a training/validation file.")
    else:
        if args.train_file is not None:
            extension = args.train_file.split(".")[-1]
            assert extension in ["csv", "json"], "`train_file` should be a csv or a json file."
        if args.validation_file is not None:
            extension = args.validation_file.split(".")[-1]
            assert extension in ["csv", "json"], "`validation_file` should be a csv or a json file."

    if args.output_dir is not None:
        os.makedirs(args.output_dir, exist_ok=True)

    return args

def main():
    args = parse_args()

    if args.source_prefix is None and args.model_name_or_path in [
        "t5-small",
        "t5-base",
        "t5-large",
        "t5-3b",
        "t5-11b",
    ]:
        logger.warning(
            "You're running a t5 model but didn't provide a source prefix, which is the expected, e.g. with "
            "`--source_prefix 'summarize: ' `"
        )
    # Initialize the accelerator. We will let the accelerator handle device placement for us in this example.
    accelerator = Accelerator()
    # Make one log on every process with the configuration for debugging.
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO,
    )
    logger.info(accelerator.state)

    # Setup logging, we only want one process per machine to log things on the screen.
    # accelerator.is_local_main_process is only True for one process per machine.
    logger.setLevel(logging.INFO if accelerator.is_local_main_process else logging.ERROR)
    if accelerator.is_local_main_process:
        datasets.utils.logging.set_verbosity_warning()
        transformers.utils.logging.set_verbosity_info()
    else:
        datasets.utils.logging.set_verbosity_error()
        transformers.utils.logging.set_verbosity_error()

    # If passed along, set the training seed now.
    if args.seed is not None:
        set_seed(args.seed)

    if accelerator.is_local_main_process and USE_WANDB:
        config = dict(
        dataset_id = "DialoGLM",
        infra = "aml",
        )
        import wandb
        wandb.init(
        project=args.wandb_exp_name,
        notes="Finetuning",
        tags=["DialoGLM"],
        config=config,
        entity= 'DialoGLM')
        wandb.run.name = args.exp_name

    # Get the datasets: you can either provide your own CSV/JSON/TXT training and evaluation files (see below)
    # or just provide the name of one of the public datasets available on the hub at https://huggingface.co/datasets/
    # (the dataset will be downloaded automatically from the datasets Hub).
    #
    # For CSV/JSON files, this script will use the column called 'text' or the first column if no column called
    # 'text' is found. You can easily tweak this behavior (see below).
    #
    # In distributed training, the load_dataset function guarantee that only one local process can concurrently
    # download the dataset.
    if args.dataset_name is not None:
        raw_datasets = load_dataset(args.dataset_name, args.dataset_config_name)
    else:
        data_files = {}
        if args.train_file is not None:
            data_files["train"] = args.train_file
        if args.validation_file is not None:
            data_files["validation"] = args.validation_file
        if args.test_file is not None:
            data_files["test"] = args.test_file
        extension = args.train_file.split(".")[-1]
        
        # Load the nested data structure
        raw_datasets = load_dataset(
            extension,
            data_files=data_files,
            field="data"  # This specifies we want to use the nested "data" field
        )
    # See more about loading any type of standard or custom dataset (from files, python dict, pandas DataFrame, etc) at
    # https://huggingface.co/docs/datasets/loading_datasets.html.

    # First load the config
    if args.config_name:
        config = AutoConfig.from_pretrained(args.config_name)
    elif args.model_name_or_path:
        config = AutoConfig.from_pretrained(args.model_name_or_path)
    else:
        config = CONFIG_MAPPING[args.model_type]()
        logger.warning("You are instantiating a new config instance from scratch.")

    # Then load tokenizer
    if args.tokenizer_name:
        tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_name, use_fast=not args.use_slow_tokenizer)
    elif args.model_name_or_path:
        tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, use_fast=not args.use_slow_tokenizer)
    else:
        raise ValueError(
            "You are instantiating a new tokenizer from scratch. This is not supported by this script."
            "You can do it from another script, save it, and load it from here, using --tokenizer_name."
        )

    # Add special tokens to tokenizer
    tokenizer.add_special_tokens({
        'additional_special_tokens': ['<|Knowledge|>', '<|Question|>', '<|Answer|>'],
        'pad_token': '[PAD]',
        'bos_token': '<s>',
        'eos_token': '</s>'
    })

    # Finally load the model
    if args.model_name_or_path:
        model = AutoModelForSeq2SeqLM.from_pretrained(
            args.model_name_or_path,
            from_tf=bool(".ckpt" in args.model_name_or_path),
            config=config,
        )
    else:
        logger.info("Training new model from scratch")
        model = AutoModelForSeq2SeqLM.from_config(config)

    # Resize token embeddings after both tokenizer and model are loaded
    model.resize_token_embeddings(len(tokenizer))

    if model.config.decoder_start_token_id is None:
        raise ValueError("Make sure that `config.decoder_start_token_id` is correctly defined")

    padding = "max_length" if args.pad_to_max_length else False
    max_target_length = args.max_target_length
    def dataset_mapping_function(examples):
        contextes = examples['context']
        questions = examples['question']
        answers = examples['answer']

        inputs = []
        for context, question in zip(contextes, questions):
            # Format the input with clear structure
            _input = f"Background: {context}\nQuestion: {question}\nProvide a direct answer:"
            inputs.append(_input)

        # Tokenize inputs
        model_inputs = tokenizer(
            inputs,
            max_length=args.max_length,
            padding=padding,
            truncation=True
        )

        # Tokenize targets (answers)
        with tokenizer.as_target_tokenizer():
            labels = tokenizer(
                answers,
                max_length=args.max_target_length,
                padding=padding,
                truncation=True
            )

        if padding == "max_length" and args.ignore_pad_token_for_loss:
            labels["labels"] = [
                [(l if l != tokenizer.pad_token_id else -100) for l in label]
                for label in labels["input_ids"]
            ]

        model_inputs["labels"] = labels["labels"]
        return model_inputs

    # Note that with `batched=True`, this map processes 1,000 texts together, so group_texts throws away a remainder
    # for each of those groups of 1,000 texts. You can adjust that batch_size here but a higher value might be slower
    # to preprocess.
    #
    # To speed up this part, we use multiprocessing. See the documentation of the map method for more information:
    # https://huggingface.co/docs/datasets/package_reference/main_classes.html#datasets.Dataset.map
    
    column_names = ['context', 'question', 'answer']
    lm_datasets = raw_datasets.map(
        dataset_mapping_function,
        batched=True,
        remove_columns=column_names,
        num_proc=args.preprocessing_num_workers,
        load_from_cache_file=False,
        desc=f"Processing dataset",
    )

    train_dataset = lm_datasets["train"]
    eval_dataset = lm_datasets["validation"]
    test_dataset = lm_datasets["test"]

    # Log a few random samples from the training set:
    for index in random.sample(range(len(train_dataset)), 1):
        logger.info(f"Sample {index} of the training set: {train_dataset[index]}.")

    label_pad_token_id = -100 if args.ignore_pad_token_for_loss else tokenizer.pad_token_id
    data_collator = DataCollatorForSeq2Seq(
        tokenizer,
        model=model,
        label_pad_token_id=label_pad_token_id,
        pad_to_multiple_of=8 if accelerator.mixed_precision != "no" else None,
    )

    def postprocess_text(preds, labels):
        preds = [normalize_answer(pred.strip()) for pred in preds]
        labels = [normalize_answer(label.strip()) for label in labels]

        return preds, labels

    train_dataloader = DataLoader(
        train_dataset, shuffle=True, collate_fn=data_collator, batch_size=args.per_device_train_batch_size
    )
    eval_dataloader = DataLoader(eval_dataset, collate_fn=data_collator, batch_size=args.per_device_eval_batch_size)
    test_dataloader = DataLoader(test_dataset, collate_fn=data_collator, batch_size=args.per_device_eval_batch_size)

    # Optimizer
    # Split weights in two groups, one with weight decay and the other not.
    no_decay = ["bias", "LayerNorm.weight"]
    optimizer_grouped_parameters = [
        {
            "params": [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)],
            "weight_decay": args.weight_decay,
        },
        {
            "params": [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)],
            "weight_decay": 0.0,
        },
    ]
    optimizer = AdamW(optimizer_grouped_parameters, lr=args.learning_rate)

    # Prepare everything with our `accelerator`.
    model, optimizer, train_dataloader, eval_dataloader, test_dataloader = accelerator.prepare(
        model, optimizer, train_dataloader, eval_dataloader, test_dataloader
    )

    # Note -> the training dataloader needs to be prepared before we grab his length below (cause its length will be
    # shorter in multiprocess)

    # Scheduler and math around the number of training steps.
    num_update_steps_per_epoch = math.ceil(len(train_dataloader) / args.gradient_accumulation_steps)
    if args.max_train_steps is None:
        args.max_train_steps = args.num_train_epochs * num_update_steps_per_epoch
    else:
        args.num_train_epochs = math.ceil(args.max_train_steps / num_update_steps_per_epoch)

    lr_scheduler = get_scheduler(
        name=args.lr_scheduler_type,
        optimizer=optimizer,
        num_warmup_steps=args.num_warmup_steps,
        num_training_steps=args.max_train_steps,
    )

    # Train!
    total_batch_size = args.per_device_train_batch_size * accelerator.num_processes * args.gradient_accumulation_steps

    logger.info("***** Running training *****")
    logger.info(f"  Num examples = {len(train_dataset)}")
    logger.info(f"  Num Epochs = {args.num_train_epochs}")
    logger.info(f"  Instantaneous batch size per device = {args.per_device_train_batch_size}")
    logger.info(f"  Total train batch size (w. parallel, distributed & accumulation) = {total_batch_size}")
    logger.info(f"  Gradient Accumulation steps = {args.gradient_accumulation_steps}")
    logger.info(f"  Total optimization steps = {args.max_train_steps}")
    # Only show the progress bar once on each machine.
    progress_bar = tqdm(range(args.max_train_steps), disable=not accelerator.is_local_main_process)
    completed_steps = 0
    global_steps = 0
    tr_loss, logging_loss = 0.0, 0.0
    for epoch in range(args.num_train_epochs):
        model.train()
        for step, batch in enumerate(train_dataloader):
            global_steps += 1            
            outputs = model(**batch)
            loss = outputs.loss
            loss = loss / args.gradient_accumulation_steps
            tr_loss += loss.item()
            accelerator.backward(loss)
            
            if step % args.gradient_accumulation_steps == 0 or step == len(train_dataloader) - 1:
                optimizer.step()
                lr_scheduler.step()
                optimizer.zero_grad()
                completed_steps += 1

            if completed_steps >= args.max_train_steps:
                break

            if step % args.logging_steps == 0:
                logger.info(f"  EVALERR:  {(tr_loss - logging_loss)/float(args.logging_steps)}")
                if accelerator.is_local_main_process and USE_WANDB:
                    wandb.log({'loss': tr_loss - logging_loss})
                logging_loss = tr_loss
                progress_bar.update(args.logging_steps)

            if args.output_dir is not None and global_steps % args.save_steps == 0 and global_steps > 0:
                accelerator.wait_for_everyone()
                if accelerator.is_local_main_process:               
                    checkpoint_prefix = 'checkpoint'
                    output_dir = os.path.join(args.output_dir, '{}-{}'.format(checkpoint_prefix, global_steps))
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    
                    # Get the model without accelerator wrapping
                    unwrapped_model = accelerator.unwrap_model(model)
                    
                    # Save model state dict directly
                    torch.save(unwrapped_model.state_dict(), os.path.join(output_dir, 'pytorch_model.bin'))
                    
                    # Save config
                    unwrapped_model.config.save_pretrained(output_dir)
                    
                    # Save tokenizer files
                    tokenizer.save_pretrained(output_dir)
                    
                    # Save training arguments
                    torch.save(args, os.path.join(output_dir, 'training_args.bin'))
                    
                    # Save generation config if it exists
                    if hasattr(unwrapped_model, 'generation_config'):
                        unwrapped_model.generation_config.save_pretrained(output_dir)
                    
                    logger.info("Saving model checkpoint to %s", output_dir)

        model.eval()

        gen_kwargs = {
            "max_length": config.max_length,
            "num_beams": args.num_beams,
        }

        def evaluate_data(dataloader, eval_name='valid'):
            metric_rouge = evaluate.load("rouge")
            metric_bleu = evaluate.load("bleu")

            decoded_preds_all = []
            for step, batch in enumerate(dataloader):
                with torch.no_grad():
                    generated_tokens = accelerator.unwrap_model(model).generate(
                        batch["input_ids"],
                        attention_mask=batch["attention_mask"],
                        **gen_kwargs,
                    )

                    generated_tokens = accelerator.pad_across_processes(
                        generated_tokens, dim=1, pad_index=tokenizer.pad_token_id
                    )
                    labels = batch["labels"]
                    if not args.pad_to_max_length:
                        labels = accelerator.pad_across_processes(batch["labels"], dim=1, pad_index=tokenizer.pad_token_id)

                    generated_tokens = accelerator.gather(generated_tokens).cpu().numpy()
                    labels = accelerator.gather(labels).cpu().numpy()

                    if args.ignore_pad_token_for_loss:
                        labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
                    if isinstance(generated_tokens, tuple):
                        generated_tokens = generated_tokens[0]
                    decoded_preds = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)
                    decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)

                    decoded_preds, decoded_labels = postprocess_text(decoded_preds, decoded_labels)
                    
                    # Format for ROUGE
                    metric_rouge.add_batch(predictions=decoded_preds, references=decoded_labels)
                    
                    # Format for BLEU - keep predictions as strings, not word lists
                    decoded_preds_all.extend(decoded_preds)
                    metric_bleu.add_batch(
                        predictions=decoded_preds,
                        references=[[x] for x in decoded_labels]
                    )
                
            result = metric_rouge.compute(use_stemmer=True)
            result = {k: round(v * 100, 4) for k, v in result.items()}
            logger.info(result)

            result_bleu = metric_bleu.compute()
            logger.info(result_bleu)

            accelerator.wait_for_everyone()
            if accelerator.is_local_main_process and USE_WANDB:
                wandb.log({f'{eval_name}_bleu': result_bleu['bleu']})
                wandb.log({f'{eval_name}_rouge': result['rougeL']})

            if args.output_dir is not None:
                accelerator.wait_for_everyone()
                if accelerator.is_local_main_process:               
                    if not os.path.exists(args.output_dir):
                        os.makedirs(args.output_dir)
                    output_dir_file_name = os.path.join(args.output_dir, f'{eval_name}-step-{completed_steps}')
                    print(output_dir_file_name)
                    json.dump(decoded_preds_all, open(output_dir_file_name,'w'), indent=2)
                    logger.info("Saving model outputs to %s", output_dir_file_name)

        evaluate_data(eval_dataloader,'valid')
        evaluate_data(test_dataloader,'test')

        if args.output_dir is not None and args.save_every_checkpoint:
            accelerator.wait_for_everyone()
            if accelerator.is_local_main_process:               
                checkpoint_prefix = 'checkpoint'
                output_dir = os.path.join(args.output_dir, '{}-epoch-{}'.format(checkpoint_prefix, completed_steps))
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                
                # Get the model without accelerator wrapping
                unwrapped_model = accelerator.unwrap_model(model)
                
                # Save model state dict directly
                torch.save(unwrapped_model.state_dict(), os.path.join(output_dir, 'pytorch_model.bin'))
                
                # Save config
                unwrapped_model.config.save_pretrained(output_dir)
                
                # Save tokenizer files
                tokenizer.save_pretrained(output_dir)
                
                # Save training arguments
                torch.save(args, os.path.join(output_dir, 'training_args.bin'))
                
                # Save generation config if it exists
                if hasattr(unwrapped_model, 'generation_config'):
                    unwrapped_model.generation_config.save_pretrained(output_dir)
                
                logger.info("Saving model checkpoint to %s", output_dir)

if __name__ == "__main__":
    main()
