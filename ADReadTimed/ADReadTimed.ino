/*
  AnalogReadSerial
 Reads an analog input on pin 0, prints the result to the serial monitor 
 
 This example code is in the public domain.
 */
#include <stdio.h>
#include <stdlib.h>
#define MAXSAMP 256
int sensorValue;
int avgValue;
int nSamp = MAXSAMP;
int sampBuf[MAXSAMP];
int sampRate = 4000; // microseconds per point
int dataReady = 0;
char inbuf[32];

void setup() {

  Serial.begin(115200);
//  Serial.println("AD_Read_Serial");
//  Serial.println("--------------");
  pinMode(A0, INPUT);
  analogReference(INTERNAL); // 1.1 V reference.
  pinMode(13, OUTPUT);
  clearSampBuf();
}

void loop() {
  int i;
  char cmd;
  if(Serial.available() > 0) {
    cmd = Serial.read();
    if (cmd == 'm') { // simple read, mean of nSamp values
      avgValue = 0;
      for (i = 0; i < nSamp; i++) {
        sensorValue = analogRead(A0);
        avgValue = avgValue + sensorValue;
      }
      avgValue = avgValue/nSamp;
      Serial.print(avgValue);
      Serial.print(", ");
      Serial.println(nSamp);
    }
    else if (cmd == 'i') { // get info
      Serial.print(nSamp);
      Serial.print(", ");
      Serial.print(sampRate);
      Serial.print(", ");
      Serial.println(dataReady);
    }
    else if (cmd == 'n') { // number of points
      nSamp = readInt();
      if (nSamp > MAXSAMP) {
        nSamp = MAXSAMP;
      }
      Serial.print("> ");
      Serial.print(nSamp);
      Serial.println("");
    }
    else if (cmd == 's') { // set sample rate, in microsecond per point
      sampRate = readInt();
      if (sampRate < 100) {
        sampRate = 100;
      }
      if (sampRate > 16383) {
        sampRate = 16383;
      }
      Serial.print("> ");
      Serial.print(sampRate);
      Serial.println("");
    }
    else if (cmd == 'a') { // acquire data
      clearSampBuf();
      for (i = 0; i < nSamp; i++) {
        sampBuf[i] = analogRead(A0);
        delayMicroseconds(sampRate);
      }
      dataReady = 1;
      blink(2);
      Serial.print("[");
      for (i = 0; i < nSamp; i++) {
        Serial.print(sampBuf[i]); 
        Serial.print(','); // (sampBuf[i]);
      }
      Serial.println("]");
    }
    else if (cmd == 'r') { // read acquired data
      Serial.print("[");
      for (i = 0; i < nSamp; i++) {
        Serial.print(sampBuf[i]);
//        if (i < nSamp-1) {
//          Serial.print(",");
//        }
      }
      Serial.println("]");
    }  
    else {
    Serial.flush();
    Serial.print("Ignored command ");
    Serial.println(cmd);
  }
  }
}

void clearSampBuf(void) {
  int i;
  for (i = 0; i < MAXSAMP; i++) {
    sampBuf[i] = 0;
  }
  dataReady = 0;  
}

void printFloat(float v) {
  union { 
    float x; 
    char c[4]; 
  } 
  fl;
  fl.x = v;
  for (int i=0; i<4; i++) {
    Serial.write(fl.c[i]);
  }
}

int readInt() {
  // Read int from serial port, terminated with ';'
  int i, num;
  int eol = 0;
  char c;
  for (i = 0; i < 32; i++) {
    inbuf[i] = 0;
  }
  i = 0;
  while (eol == 0) {
    if (Serial.available() > 0) {
      c = Serial.read();
      inbuf[i] = c;
      if (c == ';') {
        inbuf[i] = 0;
        eol = 1;
        break;
      }
      i = i + 1;
      if (i > 31) {
        eol = 1;
        break;
      }
    }
  }
  return atoi(inbuf);
}

void blink(int n) {
  int i;
  for (i = 0; i < n; i++) {
    digitalWrite(13, HIGH);
    delay(100);
    digitalWrite(13, LOW);
    delay(50);
  }
}


