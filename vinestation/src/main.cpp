#include <AS5600.h>
#include <Arduino.h>
#include <Wire.h>

AS5600 encoder;

float target_position = 0.0;
const float DEADBAND = 0.2; // Radians
const int MIN_PWM = 100;
const int MAX_PWM = 255;

// PI Controller Constants
float Kp = 50.0; // Proportional Gain
float Ki = 2.0;   // Integral Gain (start small or 0)
float integral_error = 0.0;
const float MAX_INTEGRAL = 50.0; // Integral Windup Limit

void setMotor(int pwm) {
    if (pwm > 0) {
        if (pwm < MIN_PWM) pwm = MIN_PWM;
        if (pwm > MAX_PWM) pwm = MAX_PWM;
        analogWrite(6, pwm);
        analogWrite(7, 0);
    } else if (pwm < 0) {
        pwm = -pwm;
        if (pwm < MIN_PWM) pwm = MIN_PWM;
        if (pwm > MAX_PWM) pwm = MAX_PWM;
        analogWrite(6, 0);
        analogWrite(7, pwm);
    } else {
        analogWrite(6, 0);
        analogWrite(7, 0);
    }
}

void setup() {
    // power AS5600
    pinMode(1, OUTPUT);
    pinMode(2, OUTPUT);
    digitalWrite(1, HIGH);
    digitalWrite(2, LOW);
    delay(10);

    // set up AS5600 I2C connection
    Wire.setPins(44, 43);
    Wire.begin();

    pinMode(6, OUTPUT);
    pinMode(7, OUTPUT);
    pinMode(8, OUTPUT);
    pinMode(9, OUTPUT);
    pinMode(10, OUTPUT);
    digitalWrite(8, LOW);
    digitalWrite(9, LOW);
    digitalWrite(10, LOW);
    
    analogWriteFrequency(1000);
    analogWriteResolution(8); // 0-255
    analogWrite(6, 0);
    analogWrite(7, 0);

    // wait for serial
    Serial.begin(921600); // Increased baud rate for lower latency
    while (!Serial) {
        delay(10);
    }

    if (!encoder.begin()) {
        while (1) {
            Serial.println("AS5600 not detected. Restarting...");
            delay(2000);
            ESP.restart();
        }
    }
    
    // Initialize target to current position to avoid jump on start
    target_position = (encoder.getCumulativePosition() * 2 * PI) / 4096.0;
}

void loop() {
    // Read the current angle in radians
    float current_position = (encoder.getCumulativePosition() * 2 * PI) / 4096.0;
    
    // Check for incoming serial data (target position)
    if (Serial.available() > 0) {
        String input = Serial.readStringUntil('\n');
        input.trim();
        
        // Check for GPIO command (e.g. P8:1)
        if (input.length() > 0) {
            if (input.startsWith("P")) {
                int colonIndex = input.indexOf(':');
                if (colonIndex != -1) {
                    int pin = input.substring(1, colonIndex).toInt();
                    int state = input.substring(colonIndex + 1).toInt();
                    
                    if (pin == 8 || pin == 9 || pin == 10) {
                        digitalWrite(pin, state ? HIGH : LOW);
                    }
                }
            } else {
                // Assume it's a target position (number)
                target_position = input.toFloat();
                integral_error = 0; // Reset integral on new target
            }
        }
    }

    // PI control
    float error = target_position - current_position;
    
    // Integral calculation with windup guard
    if (abs(error) > DEADBAND) {
        integral_error += error;
        if (integral_error > MAX_INTEGRAL) integral_error = MAX_INTEGRAL;
        if (integral_error < -MAX_INTEGRAL) integral_error = -MAX_INTEGRAL;
    } else {
        // Optional: Clear integral if within deadband to stop drift
        integral_error = 0;
    }

    float control_signal = (Kp * error) + (Ki * integral_error);
    
    // Invert logic based on previous user edit
    // Previous: error > 0 -> -PWM
    // Previous: error < 0 -> +PWM
    // So we negate the control signal
    int pwm_out = (int)(-control_signal);

    if (abs(error) > DEADBAND) {
        setMotor(pwm_out);
    } else {
        setMotor(0);
    }

    // Print status for GUI
    // Format: current_position
    Serial.println(current_position, 4);
    
    // Run faster
    delay(1);
}
