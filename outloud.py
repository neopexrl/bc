import qi
import argparse
import sys
import time

def main(session, answer, is_greeting=False):
    # Get the ALTextToSpeech service
    tts = session.service("ALTextToSpeech")
    
    # If this is a greeting, we can add some animation
    if is_greeting:
        # Get the ALAnimatedSpeech service for more expressive speaking
        animated_speech = session.service("ALAnimatedSpeech")
        motion_service = session.service("ALMotion")
        
        # Make sure the robot is in a good posture
        try:
            posture_service = session.service("ALRobotPosture")
            posture_service.goToPosture("Stand", 0.8)
        except Exception as e:
            print("Could not set posture: " + str(e))
        
        # Add some animation to the greeting
        try:
            # First, make sure stiffness is on
            names = ["RShoulderPitch", "RShoulderRoll", "RElbowRoll", "RElbowYaw", "RWristYaw"]
            stiffnesses = [1.0, 1.0, 1.0, 1.0, 1.0]
            motion_service.setStiffnesses(names, stiffnesses)
            
            # Use pre-defined animation for greeting
            animated_speech.say("^start(animations/Stand/Gestures/Hey_1) " + answer)
            
            # Wait for animation to finish
            time.sleep(2)
            
            # Alternatively, we can implement a custom wave using motion API
            # Uncomment this section to use custom wave instead of built-in animation
            '''
            # Prepare for wave
            motion_service.setAngles("RShoulderPitch", 0.5, 0.2)
            motion_service.setAngles("RShoulderRoll", -0.3, 0.2)
            time.sleep(1)
            
            # Do the waving motion
            for i in range(3):
                motion_service.setAngles("RElbowRoll", 0.6, 0.5)  # Open arm
                time.sleep(0.5)
                motion_service.setAngles("RElbowRoll", 1.5, 0.5)  # Close arm
                time.sleep(0.5)
            
            # Say greeting
            tts.say(answer)
            '''
            
            # Return to a neutral position
            motion_service.angleInterpolation(
                ["RShoulderPitch", "RShoulderRoll", "RElbowRoll", "RElbowYaw", "RWristYaw"],
                [[1.0], [-0.1], [0.5], [1.0], [0.0]],
                [[1.0], [1.0], [1.0], [1.0], [1.0]],
                True  # Wait for the movement to finish
            )
            
        except Exception as e:
            print("Could not perform animation: " + str(e))
            # Fall back to regular speech if animation fails
            tts.say(answer)
    else:
        # Regular answer, just say it
        print("Pepper is going to say: " + answer) 
        tts.say(answer)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", type=str, default="127.0.0.1", help="Pepper's IP address.")
    parser.add_argument("--port", type=int, default=9559, help="Naoqi port number (default: 9559)")
    parser.add_argument("answer", type=str, help="The answer to be spoken by Pepper")
    parser.add_argument("--greeting", action="store_true", help="Use greeting animation")

    args = parser.parse_args()

    # Create a session
    session = qi.Session()

    try:
        # Connect to the Pepper robot using TCP/IP
        session.connect("tcp://{}:{}".format(args.ip, args.port))  # Using .format() for string formatting in Python 2.7
    except RuntimeError:
        print("Can't connect to Naoqi at ip {} on port {}.".format(args.ip, args.port))  # Using .format() for string formatting in Python 2.7
        sys.exit(1)

    # Call the main function with the answer
    main(session, args.answer, args.greeting)