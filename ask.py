import speech_recognition as sr
import paramiko
import json
import sys
import os
import time

def get_pepper_ip():
    """Get Pepper's IP address from the user."""
    while True:
        pepper_ip = input("Please enter Pepper's IP address: ")
        if pepper_ip:
            confirm = input(f"You entered: {pepper_ip}. Is this correct? (y/n): ")
            if confirm.lower() == 'y':
                return pepper_ip
        print("Please enter a valid IP address.")

def get_voice_input():
    recognizer = sr.Recognizer()
    
    while True:
        try:
            with sr.Microphone() as source:
                print("Listening... Speak your question")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                audio = recognizer.listen(source, timeout=5)
                
            text = recognizer.recognize_google(audio)
            print(f"You asked: {text}")
            return text
            
        except sr.WaitTimeoutError:
            print("No speech detected. Please try again.")
        except sr.UnknownValueError:
            print("Could not understand the audio. Please try again.")
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
            return None
        except KeyboardInterrupt:
            print("Listening interrupted. Try again.")
            continue

def ssh_to_pepper_direct(pepper_hostname, pepper_username, pepper_password, command):
    """SSH into Pepper and execute a command directly."""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        print(f"Connecting to Pepper at {pepper_hostname}...")
        client.connect(hostname=pepper_hostname, 
                      username=pepper_username, 
                      password=pepper_password)
        
        stdin, stdout, stderr = client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        
        if exit_status != 0:
            error = stderr.read().decode('utf-8')
            print(f"Error when executing script: {error}")
        
        client.close()
        return True
    except Exception as e:
        print(f"Failed to SSH into Pepper: {str(e)}")
        return False

def make_pepper_greet(pepper_hostname, pepper_username, pepper_password):
    """Make Pepper greet the user."""
    greeting = "Hello! I am Pepper robot. What would you like to hear about FEI TUKE?"
    command = f"python2 /home/nao/pepper_codes/bilozor/outloud.py --ip localhost \"{greeting}\""
    return ssh_to_pepper_direct(pepper_hostname, pepper_username, pepper_password, command)

def ssh_to_generate(question, server_hostname="quadro.kemt.fei.tuke.sk", 
                   server_username="bilozor", server_password="studentkemt123", pepper_ip=None):
    """SSH into the server running test.py and get the answer."""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        print("Connecting to test.py server...")
        client.connect(hostname=server_hostname, 
                      username=server_username, 
                      password=server_password)
        
        # Check if conda is available and list environments
        print("Checking for conda environments...")
        stdin, stdout, stderr = client.exec_command('conda env list || echo "Conda not found"')
        conda_envs = stdout.read().decode('utf-8').strip()
        print(f"Conda environments: \n{conda_envs}")
        
        # Check if test.py exists
        stdin, stdout, stderr = client.exec_command('ls -l test.py 2>/dev/null || echo "test.py not found in current directory"')
        file_check = stdout.read().decode('utf-8').strip()
        print(f"File check: {file_check}")
        
        # Try running with conda environment and passing Pepper's IP if provided
        print("Trying to run with conda godel environment...")
        
        # Include Pepper's IP in the command if provided
        command = 'source ~/miniconda3/etc/profile.d/conda.sh && conda activate godel && python test.py'
        if pepper_ip:
            command += f' --pepper_ip {pepper_ip}'
        command += f' "{question}"'
        
        stdin, stdout, stderr = client.exec_command(command)
        error = stderr.read().decode('utf-8').strip()
        response_text = stdout.read().decode('utf-8').strip()
        
        if error:
            print(f"Command error output: {error}")
        
        if response_text:
            print("Command succeeded with output!")
            response = response_text
        else:
            print("No response from command")
            response = None
        
        client.close()
        return response
        
    except Exception as e:
        print(f"SSH connection failed: {str(e)}")
        return None

def main():
    # Configuration for server connection
    server_config = {
        "server_host": "quadro.kemt.fei.tuke.sk",
        "server_user": "bilozor",
        "server_password": "studentkemt123"
    }
    
    # Get Pepper's IP address from the user
    pepper_ip = get_pepper_ip()
    
    # Configuration for Pepper connection
    pepper_config = {
        "pepper_hostname": pepper_ip,
        "pepper_username": "nao",
        "pepper_password": "pepper"
    }
    
    # Make Pepper greet the user
    print("Sending greeting to Pepper...")
    greeting_success = make_pepper_greet(
        pepper_config["pepper_hostname"],
        pepper_config["pepper_username"],
        pepper_config["pepper_password"]
    )
    
    if greeting_success:
        print("Pepper greeted the user successfully!")
    else:
        print("Failed to make Pepper greet. Continuing with main program...")
    
    try:
        while True:
            try:
                question = get_voice_input()
                
                if not question:
                    continue
                    
                if question.lower() in ["exit", "quit", "stop"]:
                    print("Exiting...")
                    break
                
                response = ssh_to_generate(
                    question,
                    server_hostname=server_config["server_host"],
                    server_username=server_config["server_user"],
                    server_password=server_config["server_password"],
                    pepper_ip=pepper_ip  # Pass Pepper's IP to the generate script
                )
                
                if response:
                    print(f"Response received: {response}")
                else:
                    print("Failed to get response from test.py")
            except KeyboardInterrupt:
                print("\nInterrupted. Press Ctrl+C again to exit or continue speaking.")
                continue
    except KeyboardInterrupt:
        print("\nExiting program.")
        sys.exit(0)

if __name__ == "__main__":
    main()