#include <Arduino.h>
#include <ESP32Servo.h>

Servo myServo;
const int servoPin = 13;
String inputString = "";
bool stringComplete = false;

void setup() {
  Serial.begin(115200);
  myServo.attach(servoPin);
  myServo.write(90);  // Start at center position (90 degrees)
  delay(500);         // Give servo time to reach position
  
  Serial.println("Servo Control Ready");
  Serial.println("Send angle (0-180) via serial to move servo");
}

void loop() {
  // Read serial input
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    
    if (inChar == '\n' || inChar == '\r') {
      if (inputString.length() > 0) {
        stringComplete = true;
      }
    } else {
      inputString += inChar;
    }
  }
  
  // Process the command when a complete line is received
  if (stringComplete) {
    inputString.trim();
    int angle = inputString.toInt();
    
    // Validate angle range (0-180 degrees)
    if (angle >= 0 && angle <= 180) {
      myServo.write(angle);
      Serial.print("Moving servo to: ");
      Serial.print(angle);
      Serial.println(" degrees");
    } else {
      Serial.println("Error: Angle must be between 0 and 180");
    }
    
    // Clear the string for next input
    inputString = "";
    stringComplete = false;
  }
}
