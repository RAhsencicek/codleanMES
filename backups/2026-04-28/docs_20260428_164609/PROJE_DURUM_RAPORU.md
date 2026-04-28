# Codlean MES — Proje Durum Raporu

**Rapor Tarihi:** 22 Nisan 2026
**Proje Adı:** Codlean MES — Fabrika Arıza Tahmin Sistemi
**Mevcut Aşama:** Aşama 5 (Pilot)
**Çalışma Başlangıcı:** Şubat 2026
**Son Güncelleme:** 22 Nisan 2026

---

## 1. Proje Özeti

Bu sistem, fabrikadaki hidrolik pres makinelerinin sağlığını sürekli izleyip, arıza olmadan önce sizi uyaran bir erken uyarı sistemidir.

Hastanedeki hasta monitörü gibi düşünün — sürekli nabız, tansiyon, oksijen ölçer ve tehlikeli bir durum olursa hemşireyi uyarır. Bu sistem de presleriniz için aynısını yapıyor. Makinelerden gelen her veriyi anbean takip ediyor, bir şeyler ters gitmeye başladığında ise teknisyene "git bak, bir sorun oluşuyor" diyor.

**İzlenen Makineler:**

| Makine | Tip | Durum |
|--------|-----|-------|
| HPR001 | Dikey Pres | Aktif izleniyor (6 sayısal + 16 boolean sensör) |
| HPR002 | Yatay Pres | Aktif izleniyor (2 sayısal sensör) |
| HPR003 | Dikey Pres | Aktif izleniyor (6 sayısal + 16 boolean sensör) |
| HPR004 | Dikey Pres | Aktif izleniyor (6 sayısal + 16 boolean sensör) |
| HPR005 | Dikey Pres | Aktif izleniyor (6 sayısal + 16 boolean sensör) |
| HPR006 | Yatay Pres | Aktif izleniyor (2 sayısal sensör) |

Sistem, Şubat 2026'dan beri canlı ortamda çalışıyor. Temel bileşenlerin hepsi üretime alındı. Yapay zeka modeli ise hâlâ öğrenme aşamasında; veri toplama kampanyası devam ediyor.

---

## 2. Sistem Mimarisi

Sistemi bir fabrika hatı gibi düşünün. Her istasyon bir öncekinden gelen malzemeyi alır, üzerinde işlem yapar ve bir sonrakine iletir. Eğer bir istasyonda hata çıkarsa, sadece o istasyon durur, bütün fabrika çökmez.

İşte verinin fabrikadan teknisyenin ekranına ulaşana kadar geçtiği adımlar:

**Adım 1 — Veriyi Kontrol Ederiz (Katman 0)**
Fabrikadan gelen veri bazen bozuk olabiliyor. Virgülle yazılmış sayıyı noktaya çeviririz. Eski veriyi tespit ederiz. Aşırı uç değerleri yakalarız. Makine ilk çalışmaya başladığında ise ilk bir saat boyunca alarm vermeyiz çünkü o sürede değerler normalden farklı olabilir. Amaç: sağlam veriyle devam etmek.

**Adım 2 — Hafızaya Alırız (Katman 1)**
Son 2 saate ait tüm veriyi bilgisayarın hafızasında tutarız. Böylece anlık değeri değil, son iki saatin ortalamasını görürüz. Bu, tek anlık bir dalgalanmayla alarm çalmayı önler. Her 5 dakikada bir bu hafızayı diske yedekleriz; sistem yeniden başlasa bile kaybolmaz.

**Adım 3 — Analiz Ederiz (Katman 2)**
Veriyi üç açıdan inceleriz: Anlık limit kontrolü, eğilim tespiti ve fizik kuralları.
- Limit kontrolü: Sensör değeri sınırın yüzde kaçına gelmiş?
- Eğilim tespiti: Değer yukarı doğru mu gidiyor, aşağı doğru mu? Ne kadar sürede limite varır?
- Fizik kuralları: Yağ sıcaklığıyla basınç birlikte artıyorsa bu bir sorun işareti olabilir. Tek başına bakınca anlaşılmayan şeyleri birlikte değerlendiririz.

**Adım 4 — Yapay Zeka Bakar (Katman 2.5)**
Sistemin eğitilmiş bir yapay zeka modeli vardır. Bu model, geçmişteki arızaları öğrenmiştir ve yeni gelen veride benzer kalıplar arar. Model bir karar verdiğinde, bu kararı Türkçe olarak açıklayan bir metin üretiriz. Böylece teknisyen neden alarm verildiğini anlar, sadece bir sayı görmez.

**Adım 5 — Alarm Veririz (Katman 3)**
Her şey tamamsa ve gerçekten bir sorun varsa, teknisyene renkli bir alarm göndeririz. Aynı makine için gereksiz yere tekrar tekrar alarm vermeyiz. Normal durumlarda 30 dakikada bir, kritik durumlarda 15 dakikada bir alarm veririz.

**Sonuç:** Teknisyenin ekranında 2 sıra 3 sütunluk bir tablo görür. Her hücre bir makineyi temsil eder. Yeşil ise makine sağlıklı, sarı ise dikkat, kırmızı ise hemen müdahale edilmesi gerekir.

---

## 3. Tamamlanan Özellikler

Aşağıdaki özelliklerin hepsi şu an canlı ortamda çalışıyor. Her biri size ne fayda sağlıyor, açıklayalım:

**Veri Doğrulama**
Fabrikadan gelen veri bozuk olabilir. Sistem bu veriyi kontrol edip temizliyor. Sahte değerleri, eksik bilgileri, aşırı uç değerleri ayıklıyor. Böylece yanlış alarm vermiyoruz. Bir teraziyle tartarken terazinin dengede olup olmadığını kontrol etmek gibi; önce aletin doğru çalıştığından emin olursunuz.

**Hafıza Yönetimi (State Store)**
Son iki saatin verisini bilgisayar hafızasında tutuyoruz. Bu sayede ani bir dalgalanmayla panik yapmıyoruz. Ayrıca makine kaç dakikadır çalışıyor, hangi sensör ne kadar süredir aktif gibi bilgileri de takip ediyoruz. Her beş dakikada bir bunu diske kaydediyoruz; elektrik kesilse bile geri dönebiliyoruz.

**Yumuşak Limit Uyarısı**
Bir sensör limitin yüzde 85'ine geldiğinde "dikkat et, yaklaşıyorsun" diyoruz. Tam limite gelmeyi beklemez, önceden uyarır. Arabanızdaki yakıt ışığı gibi — tank tamamen boşalmadan önce yanar.

**Eğilim Tespiti**
Basınç yavaş yavaş yükseliyorsa, biz bunu fark ediyoruz. Sadece anlık değere bakmıyoruz, son yarım saatin yönünü de inceliyor. Limite ne kadar sürede varacağını hesaplıyoruz. Eğer eğilim güvenilir değilse alarm vermiyoruz.

**Risk Skoru**
Her makineye 0 ile 100 arasında bir risk puanı veriyoruz. Bu puan, limit durumu, eğilim ve fizik kurallarının birleşiminden oluşuyor. Tüm makineleri tek bir sayıyla karşılaştırabilirsiniz. Hangi makine daha riskli, bir bakışta anlaşılıyor.

**Yapay Zeka Açıklaması**
Model bir karar verdiğinde, bu kararın nedenini Türkçe olarak yazar. Örneğin: "Ana basınç son 15 dakikada yüzde 12 arttı ve yağ sıcaklığı eşik değerin üzerine çıktı." Teknisyen neden alarm verildiğini anlar ve ne yapacağını bilir.

**AI Usta Başı**
Alarm sonrası sisteme soru sorabilirsiniz. "Yağ sıcaklığı neden yükseliyor?" dediğinizde, yapay zeka geçmiş veriyi, makinenin durumunu ve fizik kurallarını bir araya getirip cevap verir. Bir deneyimli ustaya sormak gibi, ama anında cevap alırsınız.

**Akıllı Arıza Teşhisi**
Ekranda her makinenin altında küçük rozetler görürsünüz. Bu rozetler, o anda hangi fizik kuralının tetiklendiğini gösterir. Örneğin "Sinsi İç Kaçak Isısı" rozeti, yağ sıcaklığının yavaş yavaş arttığını ve bir iç kaçak olabileceğini işaret eder.

**Terminal ve Web Panelleri**
Bir tarafta renkli terminal ekranı var, teknisyen komut satırından anlık durumu görebiliyor. Diğer tarafta web tarayıcıdan açılan bir panel var; buradan tüm makineleri, geçmişi ve yapay zeka analizlerini izleyebiliyorsunuz.

**Veri Arşivleme**
Her gün gelen veriyi günün klasörüne ayrı ayrı kaydediyoruz. Böylece geçmişe dönük inceleme yapabiliyoruz. Şu ana kadar 40'ın üzerinde olayı arşivledik. Her olay, o anki sensör değerlerinin tamamını içeriyor.

**IK Senkronizasyonu**
Makine limitlerini fabrikanın IK sisteminden otomatik çekiyoruz. Limitler değiştiğinde elle dosya düzenlemeye gerek kalmıyor. Yatay ve dikey preslerin farklı limitlere sahip olduğunu da biliyoruz, doğru makineye doğru limiti uyguluyoruz.

**Boolean Sensör Takibi**
Makinelerde açık-kapalı tip sensörler var. Örneğin "pompa emiş valfi tamam" veya "yağ seviyesi düşük". Bu sensörler sürekli değişken değil, ya açık ya kapalı. Sistem bunların ne kadar süredir kapalı kaldığını takip ediyor ve gerektiğinde uyarıyor.

**Güvenli Çalışma**
Birden fazla işlem aynı anda veriye dokunuyor. Sistem bunların birbirine karışmasını önlüyor. Ayrıca yedek dosyaları yarım yazılmış olsa bile bozulmuyor; yeni dosyayı yazıp eskiyle değiştiriyoruz. Bir sigorta kutusu gibi, bir yerde sorun olursa diğerleri çalışmaya devam ediyor.

---

## 4. Devam Eden Çalışmalar

Şu anda üzerinde çalışılan şeyler ve neden yapıldıkları:

**Yapay Zeka Özellik Mühendisliği**
Neden yapılıyor? Şu anki model bazı özellikleri doğrudan limit aşımından öğreniyor. Bu, modelin aslında gerçekten tahmin yapmadığı, sadece kural tabanlı sistemin arkasından geldiği anlamına geliyor. Fabrika sorumlusu yerine bir stajyer koymuşsunuz gibi; o da ustasının yaptığını taklit ediyor, ama kendi düşünmüyor.
Bitince ne değişecek? Model, limit aşılmadan önceki davranışları öğrenecek. Sensörün son yarım saatteki artış hızı, limitin yüzde kaçına kadar çıktığı, basınçla sıcaklık arasındaki ilişki gibi gerçek sinyalleri kullanacak. Böylece arızayı önceden haber verme yeteneği artacak.

**Gerçek Fabrika Arıza Kuralları**
Neden yapılıyor? Şu anki kurallar genel hidrolik pres fizikine dayanıyor. Ama her fabrikanın kendine özgü sorunları vardır. Örneğin sizin makinelerde belirli bir basınç ve sıcaklık kombinasyonu sık sık sorun yaratıyorsa, bunu öğrenip kurala dönüştürmeliyiz.
Bitince ne değişecek? Yapay zeka usta başı size daha isabetli, fabrikanıza özel tavsiyeler verecek. "Genelde basınç artınca sıcaklık da artar" demek yerine, "sizin HPR003'te bu ikili yükselince bir saat içinde pompa sorunu yaşandı" diyecek.

**Benzer Geçmiş Olaylar**
Neden yapılıyor? Şu anda sistemin geçmiş hafızası var ama henüz yeterince veri birikmediği için kullanılmıyor. Bir doktorun 10 yıllık tecrübesiyle 1 yıllık tecrübesi arasındaki fark gibi; ne kadar çok olay görürse o kadar iyi teşhis koyar.
Bitince ne değişecek? Sistem, şu an yaşanan durumu geçmişteki benzer olaylarla karşılaştırıp "geçen ay aynı durumda yağ filtresi değişikliği gerekti" diyecek.

---

## 5. Planlanan İşler

Yapılacak işler ve bunların fabrikaya gerçek etkileri:

**Model Yeniden Eğitimi**
Etkisi: Daha az yanlış alarm, daha çok gerçek önceden uyarı. Teknisyenler gereksiz koşuşturmadan kurtulur, gerçek sorunlara odaklanır.

**Boolean Sensörlerin Modele Eklenmesi**
Etkisi: Şu anda sadece sayısal sensörleri öğreniyoruz. Ama "yağ seviyesi düşük" gibi basit ama kritik sinyalleri de öğrendiğimizde, model daha zengin bir resim görecek. Tüm makineyi değil, sadece bir parçasını izlemek yerine, bütünü izleyecek.

**Docker Containerization (Konteynerleştirme)**
Etkisi: Sistem şu anda tek bir bilgisayara bağlı. Docker ile bunu bir kutu gibi taşınabilir hale getireceğiz. Yeni bir bilgisayara geçiş 1 saat yerine 5 dakika sürecek. Fabrika genişledikçe sistemi başka makinelere de kolayca kurabileceksiniz.

**Model Sürümlendirme**
Etkisi: Her eğitilen modelin tarihini ve başarısını kaydedeceğiz. Yeni model kötü çalışırsa eskisine tek tuşla dönebileceksiniz. Yeni bir ilaç denemek gibi; işe yaramazsa eski tedaviye geri dönersiniz.

**İzleme ve Monitoring**
Etkisi: Sistemin kendi sağlığını da izleyeceğiz. Kaç alarm verdi, veri ne kadar gecikiyor, sistem yavaşladı mı? Siz makineleri izlerken, biz de sistemi izleyeceğiz. Böylece sistem çökmeye yaklaştığında önceden haber vereceğiz.

**Log Rotation (Kayıt Döngüsü)**
Etkisi: Sistem her gün binlerce satır kayıt tutuyor. Disk dolmasın diye eski kayıtları otomatik arşivleyip sileceğiz. Artık elle dosya silmekle uğraşmayacaksınız.

---

## 6. ML Model Durumu

Sistemin yapay zeka modeli bir dedektif gibi çalışıyor. Şu anki durum şöyle:

Mevcut üretim modeli, 23 Mart 2026'da eğitildi. 4.564 örnek üzerinde çalıştı. Bu örneklerin 1.116'sı arıza anına denk geliyor.

Şu an ne yapabiliyor? Eğer alarm verdiyse kesinlikle bir sorun var. Yüzde 100 isabetle gerçek sorunları yakalıyor. Ama sessiz kaldığında sorun olmadığı anlamına gelmiyor. Üç arızadan sadece birini önceden fark edebiliyor; diğer ikisini kaçırıyor.

Bu neden böyle? Çünkü model şu anda bazı özellikleri doğrudan limit aşımından öğreniyor. Yani limit aşılınca "arıza var" diyor, ama limit aşılmadan önceki davranışları öğrenemiyor. Dedektifiniz olay yerine gelince suçluyu yakalıyor, ama suç işlenmeden önce kimseyi tahmin edemiyor.

**İkinci Deneme (Geliştirilmiş Model)**
İkinci bir deneme yapıldı. Daha zengin veri özellikleri kullanıldı. Sonuç: F1 skoru yüzde 41 arttı, isabet oranı çok daha iyi hale geldi. Ama bu model henüz üretime alınmadı. Laboratuvar deneyi iyi geçti, fabrika zemininde denenmesi gerekiyor.

**Yeniden Eğitim Planı**
- Faz A (Tamamlandı): Yeterli arıza örneği toplandı.
- Faz B (Devam ediyor): Modelin gerçekten öngörü yapabilmesi için yeni veri özellikleri hazırlanıyor.
- Faz C (22-27 Nisan 2026): Yeni özelliklerle model eğitilecek. Hedef: Gerçek arızaların yüzde 85'ini önceden yakalamak.
- Faz D (27 Nisan 2026 sonrası): Sistem üretim ortamına hazır hale getirilecek.

---

## 7. Web Panelinden Neler Yapılabilir?

Sistemin web paneline tarayıcıdan girince şunları yapabilirsiniz:

**Tüm Makinelerin Anlık Durumunu Görebilirsiniz**
Altı makinenin hepsini tek ekranda görürsünüz. Her makinenin risk puanı, sensör değerleri, çalışma süresi ve aktif uyarıları bir bakışta anlaşılır. Ekran her 2 saniyede bir kendini yeniler. Yeni veri geldiğinde sayfayı elle yenilemenize gerek kalmaz.

**Yapay Zekaya Soru Sorabilirsiniz**
Bir makine seçip "Yağ sıcaklığı neden yükseliyor?" veya "Bu makine neden riskli?" diye sorabilirsiniz. Sistem, o makinenin geçmiş verisini, mevcut durumunu ve fizik kurallarını bir araya getirip Türkçe cevap verir. Aynı soruyu 10 dakika içinde tekrar sormanız durumunda hafızasındaki cevabı verir, boşuna bekletmez.

**Tüm Filonun Karşılaştırmalı Analizini Alabilirsiniz**
"Benim tüm makinelerim genel olarak nasıl?" diye bir butona basıp yapay zekadan filo raporu alabilirsiniz. Sistem, altı makineyi birbiriyle karşılaştırır, hangisi daha yorgun, hangisi dikkat ister, hangisi bakım zamanı gelmiş, hepsini tek paragrafta özetler.

**Veri Gecikmesini Kontrol Edebilirsiniz**
Fabrikadan gelen veri ne kadar eski? Ekranın köşesinde küçük bir gösterge vardır. Yeşil ise veri canlı, sarı ise birkaç dakika gecikmeli, kırmızı ise bir saatten eski veri geliyor demektir. Bu sayede "sistem çalışıyor mu?" sorusuna anında cevap alırsınız.

**Teknik Ekip İçin Ham Veri Alabilirsiniz**
Makinelerin tüm sensör değerlerini, risk puanlarını ve teşhislerini ham veri olarak çekebilirsiniz. Bu, başka bir sisteme bağlamak veya kendi raporunuzu hazırlamak isteyen teknik ekip için kullanışlıdır.

---

## 8. Sistem Nasıl Ayarlanıyor?

Sistemin davranışını birkaç parametreyle ayarlayabilirsiniz. Her birinin gerçek etkisi şöyle:

**Bayat Veri Eşiği (5 Dakika)**
Eğer bir makineden 5 dakikadan uzun süre veri gelmezse, sistem o makineyi "çevrimdışı" sayar ve alarm vermez. Neden? Çünkü eski veriye dayanarak karar vermek yanlıştır. Bir kapıcıya ev boşken alarm kurması gibi mantıksızdır.

**Başlangıç Maskesi (İlk 60 Dakika)**
Makine ilk açıldığında 60 dakika boyunca alarm vermeyiz. Çünkü makine ısınana kadar değerler normalden farklı olabilir. Sabah işe gelip bilgisayarı açar açmaz hata almak istemezsiniz; önce açılmasını beklersiniz. Aynı mantık.

**Hafıza Boyutu (Son 720 Ölçüm, Yaklaşık 2 Saat)**
Sistem son iki saatin verisini hafızada tutar. Bu, ani dalgalanmaları filtrelemek için yeterlidir. Daha kısa tutarsak geçmişi göremeyiz, daha uzun tutarsak bilgisayar yavaşlar.

**Alarm Tekrar Süresi (Normal: 30 Dakika, Kritik: 15 Dakika)**
Aynı makine için en fazla yarım saatte bir alarm verilir. Böylece alarm yorgunluğu yaşanmaz. Hastanedeki monitör her saniye ötsaydı hemşireler umursamazdı; ama gerçekten bir şey olduğunda ötmesi gerekir. Kritik durumlarda bu süre 15 dakikaya iner.

**Yumuşak Limit (Yüzde 85)**
Sensör limitin yüzde 85'ine geldiğinde sarı uyarı verilir. Tam limite beklemeden önce haber veririz. Trafikte hız sınırı 120 ise, 100'de "dikkat et" diye uyaran bir sistem gibi.

**Eğilim Güven Eşiği (R-kare: 0.70)**
Sadece güvenilir eğilimler için ETA hesaplarız. Veri çok dağınıksa "şu kadar sürede limite varır" demeyiz. Hava durumu tahmini yaparken, bir haftalık veri yerine bir yıllık veri daha güvenilir sonuç verir.

**Spike Filtresi (5 Sigma)**
Aşırı uç değerleri filtreleriz. Bir sensör anlık olarak çok yüksek değer verse bile, istatistiksel olarak anormalse görmezden geliriz. Teraziye birden rüzgar estiğinde tartımın değişmesi gibi; gerçek ağırlık değişmemiştir.

**EWMA Hassasiyeti**
Her sensörün kendi karakteri vardır. Yağ sıcaklığı yavaş değişir, basınç hızlı değişir. Sıcaklık için daha yumuşak filtre, basınç için daha sert filtre kullanırız. Böylece sıcaklığın ufak dalgalanmalarına takılmayız ama basıncın ani değişimini yakalarız.

---

## 9. Sistem Nasıl Başlatılır, Durdurulur, Kontrol Edilir?

Sistem şu anda komut satırı üzerinden yönetiliyor. İşte günlük kullanım:

**Sistemi Başlatmak**
Arka planda çalıştırmak için bir komut çalıştırırsınız. Sistem sessizce veri çekmeye ve izlemeye başlar. Ekranda renkli terminal paneli görmek isterseniz başka bir komut kullanırsınız; bu durumda terminali kapatırsanız sistem de durur.

**Sistemi Durdurmak**
Durdurma komutu verdiğinizde sistem nazikçe kapanır. Hafızasındaki veriyi diske kaydeder ve ardından durur. Bilgisayarı kapatmadan önce bu komutu vermek önemlidir; yoksa son 5 dakikanın verisi kaybolabilir.

**Durum Kontrolü**
Sistemin çalışıp çalışmadığını anlamak için durum komutu çalıştırırsınız. Size çalışan süreçlerin kimlik numaralarını gösterir. Eğer boş bir liste geliyorsa sistem kapalı demektir.

**Web Panelini Açmak**
Sistemin yanında ayrı bir pencerede web sunucusu çalıştırırsınız. Tarayıcınızda yerel adresi açtığınızda paneli görürsünüz. Web sunucusu izleme sisteminden bağımsızdır; web sunucusu çöksse bile izleme devam eder.

**Limitleri Güncellemek**
Fabrikanın IK sisteminden yeni limitler çekmek için bir komut çalıştırırsınız. Bu komut size neyin değişeceğini önceden gösterir (kuru çalıştırma). Onay verirseniz limitler güncellenir. Yatay preslerle dikey preslerin limitleri farklıdır; sistem bunu otomatik ayırır.

**Mevcut Kısıtlar**
- Sistem şu anda tek bir bilgisayarda çalışıyor. O bilgisayar kapanırsa tüm izleme durur. Yedek sistem yok.
- Log dosyaları otomatik temizlenmiyor. Zaman zaman eski logları elle silmek veya arşivlemek gerekiyor.
- Sistem macOS üzerinde geliştirildi; Linux üzerinde test edilmedi. Farklı bir işletim sistemine taşınırsa ufak ayarlamalar gerekebilir.
- Bazı komut dosyaları sabit dosya yolları kullanıyor. Başka bir klasöre taşındığında çalışmayabilir.

---

## 10. Bilinen Sorunlar ve Riskler

**Yapay Zeka Modeli Zayıf Öngörü**
Ne olabilir: Model arızayı önceden tahmin edemez, sadece limit aşıldığında haber verir.
Etkisi: Teknisyenler hâlâ acil müdahale yapmak zorunda kalır. Planlı bakım avantajından tam olarak yararlanılamaz.
Neden: Model eğitiminde kullanılan bazı veri özellikleri doğrudan limit aşımına bağlı. Model kural tabanlı sistemi taklit ediyor, kendi öngörüsünü geliştiremiyor.
Çözüm: Faz B tamamlandığında yeni özelliklerle model yeniden eğitilecek.

**Fabrikaya Özgü Kurallar Eksik**
Ne olabilir: Yapay zeka usta başı size genel hidrolik pres bilgisi verir, sizin fabrikanıza özel tavsiyelerde bulunamaz.
Etkisi: Örneğin "basınç arttı, dikkat edin" der ama "sizin makinede basınç artınca genelde pompa contası değişmeli" demez.
Neden: Bakım mühendisiyle henüz derinlemesine görüşülmedi.
Çözüm: F5-4 kapsamında bakım ekibiyle görüşülecek, edinilen bilgiler sisteme işlenecek.

**Benzer Geçmiş Olaylar Çalışmıyor**
Ne olabilir: Sistem "geçen ay buna benzer bir durum oldu" diyemez.
Etkisi: Her sorun ilk kez yaşanıyormuş gibi değerlendirilir. Tecrübenin tekrar kullanılamaması, çözüm süresini uzatır.
Neden: Yeterli veri birikmedi. Sistem Şubat'tan beri çalışıyor, daha olgunlaşması gerekiyor.
Çözüm: Zamanla veri birikecek ve bu özellik otomatik olarak devreye girecek.

**Tek İşlemci (Tek Süreç) Çalışma**
Ne olabilir: Sistem tek bir bilgisayarın tek bir işlemcisinde çalışıyor. Çok yoğun anlarda yavaşlayabilir.
Etkisi: Veri gecikmesi artabilir, alarm birkaç saniye gecikebilir. Bu genellikle sorun değil ama anlık reaksiyon gerektiren durumlarda risk oluşturabilir.
Neden: Sistem henüz birden fazla bilgisayara dağıtılacak şekilde tasarlanmadı.
Çözüm: Faz D'de Docker ile konteynerleştirme yapılacak, böylece birden fazla makineye yayılacak.

**Veri Gecikmesi**
Ne olabilir: Bazen fabrikadan gelen veri birkaç dakika gecikmeli ulaşabilir.
Etkisi: Ekranda gördüğünüz değerler anlık değil, birkaç dakika öncesine ait olabilir. Bu, çok hızlı gelişen sorunlarda geç müdahaleye neden olabilir.
Neden: Ağ altyapısı veya Kafka (veri iletim kanalı) anlık yoğunluklarda yavaşlayabilir.
Çözüm: Veri gecikmesi ekranda sürekli gösteriliyor ve izleniyor. Şu anda kabul edilebilir seviyede.

**Tek Nokta Arızası (Yedek Sistem Yok)**
Ne olabilir: Sistemin çalıştığı bilgisayar kapanırsa, arıza izleme tamamen durur.
Etkisi: Makineler çalışmaya devam eder ama siz artık uyarı almazsınız. Bir güvenlik kamerasının elektriği kesilince kayıt yapamaması gibi.
Neden: Yedek sunucu veya felaket kurtarma planı henüz kurulmadı.
Çözüm: Üretime geçiş öncesinde yedek sistem devreye alınacak.

---

## 11. Sonraki Adımlar ve Öneriler

**Bu Hafta Yapılması Gerekenler (P0)**

Bakım Mühendisi Görüşmesi: Fabrikada en sık görülen arıza kalıpları, arızadan önceki sensör davranışları ve kritik kombinasyonlar öğrenilmeli. Bu bilgiler sistemin yapay zeka kurallarına işlenecek. İş değeri: Yapay zeka size fabrikanıza özel, somut tavsiyeler vermeye başlayacak.

Yapay Zeka Özellik Mühendisliğini Tamamlamak: Modelin gerçekten öngörü yapabilmesi için yeni veri özellikleri hazırlanacak. İş değeri: Model limit aşımını değil, arıza öncesi davranışları öğrenecek. Böylece "şu an sorun var" demek yerine "bir saat içinde sorun olabilir" diyecek.

Model Eğitimi: Yeni özelliklerle model yeniden eğitilecek. Hedef: Gerçek arızaların yüzde 85'ini önceden yakalamak. İş değeri: Teknisyenler artık yangını söndürmek yerine yangını önleyecek. Acil durumlar azalacak, planlı bakım arayışları artacak.

**Kısa Vadeli (1-4 Hafta İçinde)**

Modeli Canlı Veride Doğrulamak: Yeni model laboratuvar ortamında iyi çalıştı ama fabrika zemininde de iyi çalışmalı. Gözlemleyip ayarlayacağız. İş değeri: Modelin gerçek dünyadaki performansı garanti altına alınacak.

Boolean Sensörleri Modele Eklemek: Açık-kapalı sensörler yapay zeka için yeni bir bilgi kaynağı olacak. İş değeri: Model sadece sayıları değil, makinenin durumlarını da anlayacak.

Benzer Geçmiş Olayları Aktifleştirmek: Yeterli veri birikti, artık sistemin hafızasını kullanabiliriz. İş değeri: "Geçen ay buna benzer bir durum oldu, yağ filtresi değişmişti" gibi cevaplar alacaksınız.

IK Senkronizasyonunu Düzenli Hale Getirmek: Limitleri otomatik çekmek için periyodik kontrol kurulacak. İş değeri: Elle müdahale ihtiyacı azalacak, limitler her zaman güncel kalacak.

**Orta Vadeli (1-3 Ay İçinde)**

Konteynerleştirme (Docker): Sistemi taşınabilir kutu haline getireceğiz. İş değeri: Yeni bilgisayara geçiş dakikalar içinde olacak. Fabrika büyüdükçe sistem de büyüyecek.

Model Sürümlendirme: Her eğitilen model kaydedilecek. İş değeri: Yeni model beğenilmezse eskisine anında dönülebilecek. Güvenli deneme yapılabilecek.

İzleme Panelleri: Sistemin kendi sağlığını izleyeceğiz. İş değeri: Sistem çökmeye yaklaştığında biz sizi uyarmadan önce siz bizi uyarırsınız.

Log Döngüsü: Eski kayıtlar otomatik arşivlenecek. İş değeri: Disk dolmaz, sistem yavaşlamaz, elle temizlik yapılması gerekmez.

**Üretime Geçiş Kontrol Listesi**
Şu maddeler tamamlanmadan sistem tam üretim statüsüne geçemez:
- Yapay zeka modeli hedef başarıya ulaşmalı ve kararlı çalışmalı
- Sistem konteyner haline getirilmeli ve test edilmeli
- Model sürümlendirme sistemi kurulmalı
- İzleme ve alarm altyapısı hazır olmalı
- Bakım mühendisi onaylı fabrika kuralları eklenmeli
- Kayıt döngüsü ve disk alanı izleme aktif olmalı
- Felaket kurtarma planı yazılı hale getirilmeli
- Teknik ekip eğitimini tamamlamalı

---

*Bu doküman Codlean MES projesinin resmi durum raporudur. Her önemli değişiklik sonrası güncellenmelidir.*
