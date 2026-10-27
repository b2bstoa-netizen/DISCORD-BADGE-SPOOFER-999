# ✦ 999 BADGE ✦
### Discord Profil Rozet Yöneticisi & Otomatik Kasma Aracı

Tamamen Türkçe arayüze sahip, kullanıcı dostu ve hepsi bir arada Discord profil rozet aracıdır.

---

## 🌟 Özellikler

1. **Otomatik Tarayıcı & Discord İstemci Algılama:**
   * Bilgisayarınızda açık olan Discord Masaüstü uygulaması, Chrome, Edge, Brave, Opera ve Firefox veritabanlarını tarayarak tokeninizi **otomatik olarak bulur**.
   * Manuel olarak token aramakla veya konsola yapıştırmakla uğraşmanıza gerek kalmaz (isteyen kullanıcılar için manuel giriş seçeneği de mevcuttur).

2. **Sunucu Giriş Kapısı (discord.gg/999):**
   * Uygulama, kullanıcının `https://discord.gg/999` (`1318438089001144340`) sunucusunda olup olmadığını Discord API üzerinden doğrular.
   * Sunucuda değilseniz tarayıcınızda otomatik olarak daveti açar ve katılım sağlandıktan sonra özellikleri aktif eder.

3. **🎮 Oyun Çeşitliliği Rozeti (Game Variety):**
   * İstediğiniz sayıda (örn: 100, 500 veya 999 adet) doğrulanmış oyunu tek tıkla hesabınıza işler.

4. **⏱️ Oyun Saati Rozeti (Game Time):**
   * İstediğiniz kadar saati (örn: 500, 1.000 veya 9.999 saat) hesabınıza anında ekler.

5. **🌟 Full Paket (999 Oyun & 9.999 Saat):**
   * Tek tıkla her iki rozeti de Discord'un en yüksek kademesine ulaştırır.

6. **📡 7/24 Headless Go Live (Yayın Süresi Rozeti):**
   * `discord.gg/999` sunucusundaki **1509203606887202830** ID'li ses kanalında arka planda sanal Go Live (ekran yayını) başlatır.
   * **%0 GPU ve %0 CPU harcar;** oyun açmanıza veya video oynatmanıza gerek yoktur.
   * Konsolu açık bıraktığınız sürece arka planda yayın süresi (Streaming Badge) kasar.
   * Konsolu kapattığınızda veya `q` tuşuna bastığınızda yayını otomatik ve güvenli şekilde sonlandırır.

---

## 🚀 Nasıl Başlatılır?

1. **Önemli:** Türkiye'de Discord erişim engeli olduğu için bilgisayarınızda **VPN, Cloudflare WARP veya GoodbyeDPI** açık olmalıdır.
2. Klasör içindeki **`baslat.bat`** dosyasına **çift tıklayın**.
   *(Veya terminalde `py main.py` komutunu çalıştırın).*
3. Ekrana gelen menüden yapmak istediğiniz işlemi seçin!

---

## 📁 Dosya Yapısı

* `main.py` -> Renkli Türkçe ana menü ve kullanıcı kontrol merkezi
* `baslat.bat` -> Çift tıklama ile tek tıkla başlatıcı
* `browser_auth.py` -> Tarayıcılardan ve Discord uygulamasından otomatik token ayıklayıcı
* `guild_gate.py` -> discord.gg/999 sunucu kontrolü ve yönlendirme
* `spoofer.py` -> Oyun saati ve çeşitliliği telemetri motoru
* `streamer.py` -> 7/24 Headless Go Live WebRTC yayın motoru
* `data/games.json` -> 10.426 adet doğrulanmış oyun veritabanı
* `ayarlar.json` -> Kayıtlı oturum bilgileri (tekrar giriş yapmamanız için)

---

## ⏳ Rozetler Ne Zaman Görünür?
* **Oyun Saati & Oyun Sayısı:** Discord'un telemetri analiz döngüsü genellikle **24 ila 48 saat** sürmektedir. Paketler hemen kabul edilir, profile işlenmesi bu süreyi bulur.
* **Yayın Süresi:** Discord'un medya sunucuları tarafından canlı oturum süresi olarak işlenir.
