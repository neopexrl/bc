# 🤖 Human-Machine Dialogue System with Neural Networks – FEI TUKE

This repository contains the source code and implementation details for a **neural network-based dialogue management system** integrated with the **Pepper humanoid robot**. The system was developed as part of my bachelor's thesis at the **Faculty of Electrical Engineering and Informatics**, Technical University of Košice (TUKE).

## 📄 Thesis Title

**Models for Human-Machine Dialogue Management Based on Neural Networks**  
Author: *Yevhenii Bilozor*  
Supervisor: *doc. Ing. Stanislav Ondáš, PhD.*

## 📚 Abstract

This work explores the development of a human-machine dialogue system using modern **transformer-based language models**, particularly Microsoft's **GODEL**. The model is **fine-tuned on domain-specific data** related to FEI TUKE and integrated with the **Pepper robot** for real-world interaction. The project combines theoretical foundations in NLP and dialogue systems with practical implementation, resulting in a **voice-based assistant** capable of answering questions about the faculty.

## 🚀 Features

- 🤖 Integration with Pepper robot using NAOqi SDK
- 🧠 Fine-tuned GODEL model for FEI-specific QA
- 🔊 Voice input (speech-to-text) and output (text-to-speech)
- 📚 Knowledge database (JSON format) with contextual QA pairs
- 🔄 Hybrid response system: retrieval-based + generative model
- 📈 Evaluation using BLEU and ROUGE metrics

## 🛠️ Technologies Used

- Python 3.x
- HuggingFace Transformers
- GODEL (by Microsoft Research)
- SpeechRecognition
- NAOqi SDK (Pepper robot)
- Weights & Biases (for training monitoring)
- TheFuzz (fuzzy matching)

## 🧩 Project Structure
- `generate.py` – Core logic for question answering
- `ask.py` – Speech-to-text input handling
- `outloud.py` – Text-to-speech integration with Pepper
- `train.py` – Fine-tuning script
- `README.md` 

## 🧪 Dataset and Training

- Custom-built dataset of ~30 QA pairs about the faculty
- Format: `(context, question, answer)`
- Fine-tuned over 10 epochs using HuggingFace + Accelerate
- Evaluation: BLEU score up to **0.3927** on test set

## 🧠 Inference Flow

1. User speaks into Pepper's microphone  
2. `ask.py` transcribes speech to text  
3. `generate.py` selects or generates a suitable response  
4. `outloud.py` converts the response into speech  
5. Pepper replies with synthesized voice  

## 📦 Installation

```bash
git clone https://github.com/YOUR_USERNAME/pepper-dialogue-system.git
cd pepper-dialogue-system

