import json
import torch
import paramiko
import argparse
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from thefuzz import fuzz
import sys

# Function to load the model
def load_model(model_path):
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_path)
    return tokenizer, model

# Function to load dataset
def load_dataset(json_path):
    with open(json_path, "r", encoding="utf-8") as file:
        data = json.load(file)["data"]
    return data

# Find answer from dataset based on the question and keywords
def find_answer(question, dataset, keywords, threshold=80):
    if any(keyword.lower() in question.lower() for keyword in keywords):
        question_tokens = set(question.lower().split())
        for entry in dataset:
            if question.lower() == entry["question"].lower():
                return entry["answer"], 100  # Exact match
        
        best_match = None
        best_score = 0
        
        for entry in dataset:
            base_score = fuzz.ratio(question.lower(), entry["question"].lower())
            entry_tokens = set(entry["question"].lower().split())
            common_words = question_tokens.intersection(entry_tokens)
            topic_boost = 10 if len(common_words) >= 2 else 0
            
            question_types = {
                "when": ["when", "established", "founded", "created", "year", "date"],
                "where": ["where", "located", "address", "city"],
                "who": ["who", "person", "people", "faculty"],
                "what": ["what", "purpose", "description"]
            }

            user_q_type = None
            for q_type, indicators in question_types.items():
                if any(ind in question.lower() for ind in indicators):
                    user_q_type = q_type
                    break
            
            entry_q_type = None
            for q_type, indicators in question_types.items():
                if any(ind in entry["question"].lower() for ind in indicators):
                    entry_q_type = q_type
                    break
            
            type_boost = 15 if user_q_type and user_q_type == entry_q_type else 0
            final_score = base_score + topic_boost + type_boost
            
            if final_score > best_score and final_score >= threshold:
                best_match = entry["answer"]
                best_score = final_score
        
        if best_match:
            return best_match, best_score
        return "I couldn't find a relevant answer in the dataset.", 0
    
    return None, 0

# Function to generate response using the model
def generate_response(question, model, tokenizer, max_length=100):
    inputs = tokenizer(question, return_tensors="pt")
    with torch.no_grad():
        outputs = model.generate(**inputs, max_length=max_length)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

# SSH into Pepper and make it say the generated answer
def ssh_to_pepper(pepper_hostname, pepper_username, pepper_password, answer):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        print(f"Connecting to Pepper at {pepper_hostname}...")
        client.connect(hostname=pepper_hostname, 
                      username=pepper_username, 
                      password=pepper_password)

        command = f"python2 /home/nao/pepper_codes/bilozor/outloud.py --ip localhost \"{answer}\""
        stdin, stdout, stderr = client.exec_command(command)

        exit_status = stdout.channel.recv_exit_status()

        if exit_status == 0:
            print("Pepper successfully spoke the answer.")
        else:
            error = stderr.read().decode('utf-8')
            print(f"Error when executing script: {error}")

        client.close()
    except Exception as e:
        print(f"Failed to SSH into Pepper: {str(e)}")

# Main function to drive the entire process
def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Question answering system for Pepper robot")
    parser.add_argument("question", type=str, help="The question to answer")
    parser.add_argument("--pepper_ip", type=str, help="Pepper robot's IP address")
    args = parser.parse_args()
    
    # Model and dataset paths
    model_path = "./godel_finetuned_fixed/checkpoint-100"
    dataset_path = "./fei_tuke_dataset.json"
    
    # Keywords for dataset search
    keywords = ["Faculty", "Košice", "Electrical Engineering", "Informatics", 
               "departments", "research", "established", "founded", "created", 
               "year", "date", "when"]
    
    # Pepper robot SSH credentials
    pepper_config = {
        "pepper_hostname": args.pepper_ip if args.pepper_ip else "147.232.156.65",  # Use provided IP or default
        "pepper_username": "nao",
        "pepper_password": "pepper",
        "pepper_port": 22
    }
    
    # Load model and dataset
    print("Loading model and dataset...")
    tokenizer, model = load_model(model_path)
    dataset = load_dataset(dataset_path)
    print("Ready to answer questions!")
    
    question = args.question
    answer, confidence_score = find_answer(question, dataset, keywords)
    final_answer = ""
    
    if answer:
        if confidence_score >= 90:
            final_answer = answer
        elif confidence_score >= 75:
            final_answer = answer
        else:
            response = generate_response(question, model, tokenizer)
            final_answer = response
    else:
        response = generate_response(question, model, tokenizer)
        final_answer = response
    
    print(final_answer)
    ssh_to_pepper(
        pepper_config["pepper_hostname"],
        pepper_config["pepper_username"],
        pepper_config["pepper_password"],
        final_answer
    )

if __name__ == "__main__":
    main()