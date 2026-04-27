# Requirements Document

## Pendahuluan

Chess Video Translator adalah tool otomasi berbasis Python yang menerjemahkan video analisis catur berbahasa Indonesia menjadi video dengan suara bahasa Inggris dan subtitle bahasa Inggris yang tersinkronisasi. Tool ini beroperasi melalui antarmuka Telegram Bot dan berjalan di VPS dengan CPU only (tanpa GPU). Pipeline utama meliputi: ekstraksi audio, speech-to-text (Indonesia), terjemahan teks (Indonesia → Inggris), text-to-speech (Inggris), dan penggabungan ulang video dengan audio baru serta subtitle.

## Glossary

- **Telegram_Bot**: Antarmuka bot Telegram yang menerima video input dari pengguna dan mengirimkan video hasil terjemahan kembali ke pengguna.
- **Pipeline_Processor**: Komponen utama yang mengorkestrasi seluruh tahapan pemrosesan video dari awal hingga akhir.
- **Audio_Extractor**: Modul yang mengekstrak track audio dari file video menggunakan FFmpeg.
- **Speech_Recognizer**: Modul speech-to-text yang menggunakan faster-whisper dalam mode CPU untuk mengonversi audio bahasa Indonesia menjadi teks bertimestamp.
- **Translator**: Modul penerjemah yang menerjemahkan teks dari bahasa Indonesia ke bahasa Inggris per segmen.
- **Speech_Synthesizer**: Modul text-to-speech yang menghasilkan audio bahasa Inggris dari teks terjemahan menggunakan edge-tts, dengan durasi yang disesuaikan per segmen.
- **Subtitle_Generator**: Modul yang menghasilkan file subtitle SRT bahasa Inggris berdasarkan segmen terjemahan bertimestamp.
- **Video_Merger**: Modul yang menggabungkan video asli dengan audio terjemahan baru dan membakar (burn-in) subtitle bahasa Inggris menggunakan FFmpeg.
- **Drive_Manager**: Modul yang mengelola upload dan download file dari/ke Google Drive untuk file yang melebihi batas ukuran Telegram (50MB).
- **Segment**: Satu unit teks hasil speech-to-text yang memiliki timestamp mulai dan timestamp selesai, beserta teks transkripsi.
- **SRT**: SubRip Subtitle, format file subtitle standar yang berisi nomor urut, timestamp, dan teks subtitle.

## Requirements

### Requirement 1: Penerimaan Video via Telegram Bot

**User Story:** Sebagai kreator konten catur, saya ingin mengirim video analisis catur saya melalui Telegram Bot, sehingga saya dapat memproses terjemahan dengan mudah tanpa antarmuka yang rumit.

#### Acceptance Criteria

1. WHEN pengguna mengirim file video melalui chat Telegram, THE Telegram_Bot SHALL menerima file video tersebut dan menyimpannya ke penyimpanan lokal sementara untuk diproses.
2. WHEN pengguna mengirim pesan berisi link Google Drive yang valid, THE Telegram_Bot SHALL mengunduh file video dari Google Drive ke penyimpanan lokal sementara.
3. WHEN pengguna mengirim file yang bukan format video yang didukung (selain MP4, AVI, MKV, MOV, WEBM), THE Telegram_Bot SHALL mengirim pesan error yang menjelaskan format video yang didukung.
4. WHEN pengguna mengirim pesan tanpa file video atau link Google Drive, THE Telegram_Bot SHALL mengirim pesan panduan penggunaan bot.
5. IF link Google Drive yang dikirim pengguna tidak dapat diakses atau tidak valid, THEN THE Telegram_Bot SHALL mengirim pesan error yang menjelaskan bahwa link tidak dapat diakses beserta instruksi untuk memastikan file di-share secara publik.

### Requirement 2: Ekstraksi Audio dari Video

**User Story:** Sebagai sistem, saya perlu mengekstrak track audio dari video input, sehingga audio dapat diproses oleh modul speech-to-text.

#### Acceptance Criteria

1. WHEN file video diterima untuk diproses, THE Audio_Extractor SHALL mengekstrak track audio dari video menggunakan FFmpeg dan menyimpannya sebagai file WAV mono 16kHz.
2. IF file video tidak memiliki track audio, THEN THE Audio_Extractor SHALL melaporkan error ke Pipeline_Processor dengan pesan bahwa video tidak mengandung audio.
3. IF proses ekstraksi audio gagal karena file video corrupt, THEN THE Audio_Extractor SHALL melaporkan error ke Pipeline_Processor dengan pesan bahwa file video tidak dapat diproses.

### Requirement 3: Speech-to-Text Bahasa Indonesia

**User Story:** Sebagai sistem, saya perlu mengonversi audio bahasa Indonesia menjadi teks bertimestamp, sehingga setiap segmen pembicaraan dapat diterjemahkan secara terpisah dengan timing yang tepat.

#### Acceptance Criteria

1. WHEN file audio diterima, THE Speech_Recognizer SHALL melakukan transkripsi menggunakan faster-whisper dalam mode CPU dengan model "small" dan bahasa sumber "id" (Indonesia).
2. THE Speech_Recognizer SHALL menghasilkan daftar Segment, di mana setiap Segment berisi timestamp mulai (detik), timestamp selesai (detik), dan teks transkripsi bahasa Indonesia.
3. WHEN transkripsi selesai, THE Speech_Recognizer SHALL memastikan setiap Segment memiliki durasi minimal 0.5 detik dan maksimal 15 detik.
4. IF audio tidak mengandung ucapan yang dapat dikenali, THEN THE Speech_Recognizer SHALL melaporkan error ke Pipeline_Processor dengan pesan bahwa tidak ada ucapan yang terdeteksi.

### Requirement 4: Terjemahan Teks Indonesia ke Inggris

**User Story:** Sebagai sistem, saya perlu menerjemahkan setiap segmen teks dari bahasa Indonesia ke bahasa Inggris, sehingga konten analisis catur dapat dipahami oleh audiens internasional.

#### Acceptance Criteria

1. WHEN daftar Segment dengan teks bahasa Indonesia diterima, THE Translator SHALL menerjemahkan teks setiap Segment dari bahasa Indonesia ke bahasa Inggris.
2. THE Translator SHALL mempertahankan timestamp mulai dan timestamp selesai dari setiap Segment asli pada Segment hasil terjemahan.
3. IF terjemahan satu Segment gagal, THEN THE Translator SHALL menggunakan teks asli bahasa Indonesia sebagai fallback untuk Segment tersebut dan melanjutkan pemrosesan Segment berikutnya.
4. THE Translator SHALL menerjemahkan istilah catur standar (seperti "kuda", "benteng", "gajah", "menteri", "raja", "skak mat") ke padanan bahasa Inggris yang benar ("knight", "rook", "bishop", "queen", "king", "checkmate").

### Requirement 5: Text-to-Speech Bahasa Inggris Tersinkronisasi

**User Story:** Sebagai kreator konten catur, saya ingin suara terjemahan bahasa Inggris tersinkronisasi dengan posisi papan catur di video, sehingga penjelasan audio cocok dengan apa yang ditampilkan di layar.

#### Acceptance Criteria

1. WHEN Segment terjemahan bahasa Inggris diterima, THE Speech_Synthesizer SHALL menghasilkan audio bahasa Inggris untuk setiap Segment menggunakan edge-tts.
2. THE Speech_Synthesizer SHALL menyesuaikan kecepatan (rate) audio TTS agar durasi audio yang dihasilkan sesuai dengan durasi Segment asli (selisih maksimal 0.3 detik).
3. IF durasi audio TTS yang dihasilkan melebihi durasi Segment asli setelah penyesuaian rate, THEN THE Speech_Synthesizer SHALL memotong (trim) audio TTS agar sesuai dengan durasi Segment asli.
4. IF durasi audio TTS yang dihasilkan lebih pendek dari durasi Segment asli setelah penyesuaian rate, THEN THE Speech_Synthesizer SHALL menambahkan silence padding di akhir agar sesuai dengan durasi Segment asli.
5. WHEN semua Segment telah diproses, THE Speech_Synthesizer SHALL menggabungkan seluruh audio Segment menjadi satu track audio lengkap dengan silence di antara Segment sesuai gap timestamp asli.

### Requirement 6: Pembuatan Subtitle Bahasa Inggris

**User Story:** Sebagai kreator konten catur, saya ingin subtitle bahasa Inggris ditampilkan di video, sehingga penonton dapat membaca terjemahan bersamaan dengan mendengar audio.

#### Acceptance Criteria

1. WHEN daftar Segment terjemahan bahasa Inggris tersedia, THE Subtitle_Generator SHALL menghasilkan file subtitle dalam format SRT.
2. THE Subtitle_Generator SHALL memastikan setiap entri subtitle memiliki timestamp mulai dan timestamp selesai yang sesuai dengan Segment asli.
3. THE Subtitle_Generator SHALL memastikan setiap baris subtitle tidak melebihi 42 karakter, dan memecah teks yang lebih panjang menjadi beberapa baris dalam satu entri subtitle.
4. FOR ALL Segment terjemahan yang valid, parsing file SRT yang dihasilkan lalu memformat ulang lalu parsing kembali SHALL menghasilkan objek subtitle yang ekuivalen (round-trip property).

### Requirement 7: Penggabungan Video Final

**User Story:** Sebagai kreator konten catur, saya ingin mendapatkan video final dengan audio bahasa Inggris dan subtitle yang sudah di-burn-in, sehingga video siap dipublikasikan untuk audiens internasional.

#### Acceptance Criteria

1. WHEN track audio terjemahan dan file subtitle SRT tersedia, THE Video_Merger SHALL menggabungkan video asli dengan track audio baru menggunakan FFmpeg, menggantikan track audio asli.
2. THE Video_Merger SHALL membakar (hardcode/burn-in) subtitle bahasa Inggris ke dalam video menggunakan filter subtitle FFmpeg.
3. THE Video_Merger SHALL menghasilkan video output dalam format MP4 dengan codec H.264 untuk video dan AAC untuk audio.
4. IF proses penggabungan gagal, THEN THE Video_Merger SHALL melaporkan error ke Pipeline_Processor dengan detail penyebab kegagalan.
5. THE Video_Merger SHALL memastikan durasi video output sama dengan durasi video input (selisih maksimal 1 detik).

### Requirement 8: Pengiriman Hasil via Telegram Bot

**User Story:** Sebagai kreator konten catur, saya ingin menerima video hasil terjemahan kembali melalui Telegram, sehingga saya dapat langsung mengunduh dan mempublikasikannya.

#### Acceptance Criteria

1. WHEN video hasil pemrosesan berukuran 50MB atau kurang, THE Telegram_Bot SHALL mengirim file video langsung ke pengguna melalui chat Telegram.
2. WHEN video hasil pemrosesan berukuran lebih dari 50MB, THE Telegram_Bot SHALL mengupload video ke Google Drive dan mengirim link Google Drive ke pengguna melalui chat Telegram.
3. WHEN pemrosesan video dimulai, THE Telegram_Bot SHALL mengirim pesan status progres ke pengguna yang menunjukkan tahap pemrosesan saat ini (ekstraksi audio, transkripsi, terjemahan, sintesis suara, penggabungan).
4. IF pemrosesan video gagal di tahap manapun, THEN THE Telegram_Bot SHALL mengirim pesan error yang informatif ke pengguna yang menjelaskan tahap mana yang gagal.

### Requirement 9: Integrasi Google Drive

**User Story:** Sebagai kreator konten catur, saya ingin dapat mengirim dan menerima video berukuran besar melalui Google Drive, sehingga saya tidak terbatas oleh limit ukuran file Telegram.

#### Acceptance Criteria

1. WHEN link Google Drive diterima untuk download, THE Drive_Manager SHALL mengautentikasi menggunakan service account credentials dan mengunduh file ke penyimpanan lokal.
2. WHEN file video hasil pemrosesan perlu diupload, THE Drive_Manager SHALL mengupload file ke folder Google Drive yang dikonfigurasi dan mengembalikan link yang dapat dibagikan (shareable link).
3. IF autentikasi Google Drive gagal, THEN THE Drive_Manager SHALL melaporkan error ke Pipeline_Processor dengan pesan bahwa koneksi ke Google Drive gagal.
4. IF download dari Google Drive gagal karena file tidak ditemukan atau tidak dapat diakses, THEN THE Drive_Manager SHALL melaporkan error ke Pipeline_Processor dengan pesan yang menjelaskan penyebab kegagalan.
5. THE Drive_Manager SHALL mendukung download file dari link Google Drive dengan format "https://drive.google.com/file/d/{file_id}" dan "https://drive.google.com/open?id={file_id}".

### Requirement 10: Orkestrasi Pipeline dan Manajemen Resource

**User Story:** Sebagai sistem, saya perlu mengorkestrasi seluruh tahapan pemrosesan secara berurutan dan mengelola file sementara, sehingga pemrosesan berjalan efisien di VPS dengan resource terbatas.

#### Acceptance Criteria

1. THE Pipeline_Processor SHALL menjalankan tahapan pemrosesan secara berurutan: ekstraksi audio → speech-to-text → terjemahan → text-to-speech → pembuatan subtitle → penggabungan video.
2. WHEN pemrosesan video selesai (berhasil atau gagal), THE Pipeline_Processor SHALL menghapus semua file sementara yang dibuat selama pemrosesan.
3. WHILE pemrosesan video sedang berlangsung, THE Pipeline_Processor SHALL melaporkan tahap pemrosesan saat ini ke Telegram_Bot untuk diteruskan ke pengguna.
4. THE Pipeline_Processor SHALL memproses satu video pada satu waktu untuk menghindari kelebihan beban pada VPS dengan CPU only.
5. IF pemrosesan video melebihi batas waktu 30 menit, THEN THE Pipeline_Processor SHALL membatalkan pemrosesan dan melaporkan timeout ke Telegram_Bot.
