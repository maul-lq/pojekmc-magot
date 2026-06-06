#include <DHT.h>
#include <WiFi.h>
#include <PubSubClient.h>

// Konfigurasi Pin
#define DHTPIN 14
#define DHTTYPE DHT22
#define MQ_PIN 34
#define BUZZER_PIN 13 // Mengubah nama dari RELAY_PIN menjadi BUZZER_PIN

// ---------------------------------------------------------
// KONFIGURASI WIFI & MQTT (GANTI SESUAI JARINGAN KAMU)
// ---------------------------------------------------------
const char* ssid = "TANU";
const char* password = "55555555";

const char* mqtt_server = "192.168.18.43";
const int mqtt_port = 1883;
const char* mqtt_user = ""; 
const char* mqtt_password = "";
const char* mqtt_topic = "esp32/sensor_data";
// ---------------------------------------------------------

DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient client(espClient);

unsigned long lastMsg = 0; // Untuk interval pembacaan sensor (2 detik)

// --- KONFIGURASI ASYNC BUZZER (BISA DIKUSTOMISASI) ---
bool buzzerActive = false;          // Status apakah buzzer harus berbunyi atau tidak
unsigned long lastBuzzerToggle = 0; // Timer internal untuk pola buzzer
int currentBuzzerStep = 0;          // Langkah pola yang sedang berjalan
bool lastBuzzerState = false;       // Menyimpan status aktif sebelumnya

// Kustomisasi Pola Bunyi di Sini:
// Isi dengan frekuensi (Hz). Angka 0 berarti jeda/diam (silent).
const int buzzerPatternFreq[] = {2000, 0, 2500, 0, 3000, 0}; 
// Durasi untuk masing-masing frekuensi di atas (dalam milidetik)
const int buzzerPatternDuration[] = {150, 100, 150, 100, 150, 400}; 

// Hitung total langkah dalam pola secara otomatis
const int totalBuzzerSteps = sizeof(buzzerPatternFreq) / sizeof(buzzerPatternFreq[0]);
// -----------------------------------------------------

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);
    
    if (client.connect(clientId.c_str(), mqtt_user, mqtt_password)) {
      Serial.println("connected to Mosquitto");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000); 
    }
  }
}

// Fungsi non-blocking untuk mengatur bunyi buzzer secara asinkronus
void updateBuzzer() {
  if (!buzzerActive) {
    if (lastBuzzerState) { // Jika baru saja berubah dari aktif ke mati
      noTone(BUZZER_PIN);
      lastBuzzerState = false;
    }
    return;
  }

  unsigned long currentMillis = millis();

  // Jika baru aktif pertama kali, mulai dari langkah 0
  if (!lastBuzzerState) {
    lastBuzzerState = true;
    currentBuzzerStep = 0;
    lastBuzzerToggle = currentMillis;
    
    if (buzzerPatternFreq[currentBuzzerStep] == 0) {
      noTone(BUZZER_PIN);
    } else {
      tone(BUZZER_PIN, buzzerPatternFreq[currentBuzzerStep]);
    }
    return;
  }

  // Cek apakah durasi langkah aktif saat ini sudah habis
  if (currentMillis - lastBuzzerToggle >= buzzerPatternDuration[currentBuzzerStep]) {
    lastBuzzerToggle = currentMillis;
    
    // Lanjut ke langkah pola berikutnya (looping kembali ke 0 jika sudah selesai)
    currentBuzzerStep = (currentBuzzerStep + 1) % totalBuzzerSteps;
    
    if (buzzerPatternFreq[currentBuzzerStep] == 0) {
      noTone(BUZZER_PIN);
    } else {
      tone(BUZZER_PIN, buzzerPatternFreq[currentBuzzerStep]);
    }
  }
}

void setup() {
  Serial.begin(115200);

  dht.begin();
  pinMode(BUZZER_PIN, OUTPUT);
  noTone(BUZZER_PIN); // Pastikan buzzer mati saat startup

  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // Jalankan fungsi update buzzer secara berkala (Asinkronus)
  updateBuzzer();

  // Jalankan eksekusi sensor setiap 2000ms (2 detik) tanpa memblokir loop
  unsigned long now = millis();
  if (now - lastMsg > 2000) {
    lastMsg = now;

    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();
    int gasValue = analogRead(MQ_PIN);
    String buzzerStateStr = "OFF";

    Serial.println("==========");

    if (!isnan(temperature) && !isnan(humidity)) {
      Serial.print("Temperature: ");
      Serial.print(temperature);
      Serial.println(" °C");

      Serial.print("Humidity: ");
      Serial.print(humidity);
      Serial.println(" %");
    } else {
      Serial.println("DHT22 Read Error");
      temperature = 0; 
      humidity = 0;
    }

    Serial.print("Gas Value: ");
    Serial.println(gasValue);

    // Buzzer Logic (Hanya mengubah flag active, eksekusi suara ada di updateBuzzer)
    if (!(temperature > 29 || temperature < 39) || gasValue > 2000) {
      buzzerActive = true;
      buzzerStateStr = "ON";
      Serial.println("Buzzer Status: ACTIVE");
    } else {
      buzzerActive = false;
      buzzerStateStr = "OFF";
      Serial.println("Buzzer Status: INACTIVE");
    }

    // --- PUBLISH DATA KE MOSQUITTO ---
    String payload = "{";
    payload += "\"temperature\":" + String(temperature) + ",";
    payload += "\"humidity\":" + String(humidity) + ",";
    payload += "\"gas\":" + String(gasValue) + ",";
    payload += "\"buzzer\":\"" + buzzerStateStr + "\""; // Mengubah key JSON menjadi buzzer
    payload += "}";

    client.publish(mqtt_topic, payload.c_str());
    Serial.print("Data Published: ");
    Serial.println(payload);
  }
}