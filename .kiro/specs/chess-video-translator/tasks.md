# Implementation Plan: Chess Video Translator

## Overview

Implementasi pipeline otomasi Python untuk menerjemahkan video analisis catur berbahasa Indonesia menjadi video dengan audio bahasa Inggris dan subtitle burn-in, diakses melalui Telegram Bot. Setiap task membangun di atas task sebelumnya secara inkremental, dimulai dari setup project, data models, modul-modul pipeline, hingga integrasi akhir.

## Tasks

- [x] 1. Setup project structure dan dependencies
  - Buat struktur direktori: `src/`, `tests/`, `tests/test_properties/`, `tests/test_unit/`, `tests/test_integration/`
  - Buat `pyproject.toml` dengan dependencies: `python-telegram-bot>=20.0`, `faster-whisper`, `deep-translator`, `edge-tts`, `pysrt`, `google-api-python-client`, `google-auth`, `hypothesis`, `pytest`, `pytest-asyncio`
  - Buat `src/__init__.py` dan `tests/conftest.py` kosong
  - _Requirements: 10.1_

- [x] 2. Implementasi data models dan konfigurasi
  - [x] 2.1 Buat data models (`src/models.py`)
    - Implementasi dataclass `Segment` (frozen, dengan property `duration`)
    - Implementasi dataclass `TranslatedSegment` (frozen, dengan property `duration`)
    - Implementasi enum `PipelineStage` dengan semua tahapan
    - Implementasi dataclass `PipelineResult` dan `JobContext`
    - _Requirements: 3.2, 4.2, 10.1_

  - [x] 2.2 Buat konfigurasi dan konstanta (`src/config.py`)
    - Implementasi dataclass `AppConfig` dengan semua field konfigurasi
    - Definisikan `SUPPORTED_VIDEO_EXTENSIONS`, `GOOGLE_DRIVE_PATTERNS`, `CHESS_TERM_MAPPING`
    - Implementasi fungsi `load_config()` yang membaca dari environment variables
    - _Requirements: 1.3, 4.4, 9.5_

  - [x] 2.3 Buat error hierarchy (`src/errors.py`)
    - Implementasi `ChessTranslatorError` sebagai base exception
    - Implementasi semua exception turunan: `AudioExtractionError`, `TranscriptionError`, `TranslationError`, `TTSSynthesisError`, `SubtitleError`, `VideoMergeError`, `DriveError`, `DriveDownloadError`, `DriveUploadError`, `PipelineError` (dengan atribut `stage`)
    - _Requirements: 2.2, 2.3, 3.4, 7.4, 8.4, 9.3, 9.4_

  - [ ]* 2.4 Write property test: Video Format Validation
    - **Property 1: Video Format Validation**
    - Untuk setiap string ekstensi file, fungsi validasi menerima jika dan hanya jika ekstensi lowercase ada di set {".mp4", ".avi", ".mkv", ".mov", ".webm"}
    - **Validates: Requirements 1.3**

  - [ ]* 2.5 Write unit tests untuk data models dan config
    - Test `Segment.duration` dan `TranslatedSegment.duration` dengan contoh spesifik
    - Test `load_config()` dengan environment variables
    - Test validasi format video dengan contoh valid dan invalid
    - _Requirements: 3.2, 1.3_

- [x] 3. Implementasi Audio Extractor
  - [x] 3.1 Buat `src/audio_extractor.py`
    - Implementasi class `AudioExtractor` dengan method `extract(video_path, output_path) -> Path`
    - Gunakan `subprocess.run` untuk menjalankan FFmpeg: konversi ke WAV mono 16kHz
    - Handle error: file corrupt → `AudioExtractionError`, tidak ada audio track → `AudioExtractionError`
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ]* 3.2 Write unit tests untuk Audio Extractor
    - Test FFmpeg command construction
    - Test error handling untuk file tanpa audio track
    - Test error handling untuk file corrupt (mock subprocess)
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 4. Implementasi Speech Recognizer
  - [x] 4.1 Buat `src/speech_recognizer.py`
    - Implementasi class `SpeechRecognizer` dengan `__init__(model_size, device)` dan method `transcribe(audio_path) -> list[Segment]`
    - Gunakan `faster-whisper` dengan model "small", device "cpu", bahasa "id"
    - Implementasi fungsi normalisasi durasi: split segmen >15 detik, merge segmen <0.5 detik
    - Raise `TranscriptionError` jika tidak ada ucapan terdeteksi
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 4.2 Write property test: Segment Structural Invariants
    - **Property 2: Segment Structural Invariants**
    - Untuk setiap Segment yang dihasilkan, `start < end`, `duration > 0`, dan `text` non-empty
    - **Validates: Requirements 3.2**

  - [ ]* 4.3 Write property test: Segment Duration Normalization
    - **Property 3: Segment Duration Normalization**
    - Setelah normalisasi, setiap segmen memiliki durasi antara 0.5 dan 15 detik (inklusif)
    - **Validates: Requirements 3.3**

  - [ ]* 4.4 Write unit tests untuk Speech Recognizer
    - Test transkripsi dengan mock faster-whisper model
    - Test normalisasi durasi dengan segmen terlalu panjang dan terlalu pendek
    - Test error ketika tidak ada ucapan terdeteksi
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 5. Checkpoint - Pastikan semua test lulus
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implementasi Translator
  - [x] 6.1 Buat `src/translator.py`
    - Implementasi class `ChessTranslator` dengan `CHESS_TERMS` mapping
    - Implementasi method `translate_segments(segments) -> list[TranslatedSegment]`
    - Implementasi method `translate_text(text) -> str` menggunakan `deep-translator` GoogleTranslator
    - Implementasi method `_apply_chess_terms(text) -> str` untuk pre-processing istilah catur dengan placeholder
    - Implementasi fallback: jika terjemahan satu segmen gagal, gunakan teks asli
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 6.2 Write property test: Timestamp Preservation During Translation
    - **Property 4: Timestamp Preservation During Translation**
    - Setelah terjemahan, setiap `TranslatedSegment` memiliki `start` dan `end` identik dengan `Segment` asli
    - **Validates: Requirements 4.2**

  - [ ]* 6.3 Write property test: Translation Fallback on Failure
    - **Property 5: Translation Fallback on Failure**
    - Jika terjemahan gagal untuk subset segmen, output tetap memiliki jumlah segmen sama dengan input, dan segmen gagal menggunakan teks asli
    - **Validates: Requirements 4.3**

  - [ ]* 6.4 Write property test: Chess Term Mapping Correctness
    - **Property 6: Chess Term Mapping Correctness**
    - Untuk teks yang mengandung istilah catur Indonesia, `_apply_chess_terms` mengganti semua istilah dengan padanan Inggris yang benar
    - **Validates: Requirements 4.4**

  - [ ]* 6.5 Write unit tests untuk Translator
    - Test terjemahan istilah catur spesifik: "kuda" → "knight", "benteng" → "rook", dll
    - Test fallback ketika GoogleTranslator gagal (mock exception)
    - Test `_apply_chess_terms` dengan teks campuran istilah catur dan teks biasa
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 7. Implementasi Speech Synthesizer
  - [x] 7.1 Buat `src/speech_synthesizer.py`
    - Implementasi class `SpeechSynthesizer` dengan `__init__(voice)` default "en-US-AriaNeural"
    - Implementasi async method `synthesize_segments(segments, output_path) -> Path`
    - Implementasi async method `synthesize_single(text, target_duration, output_path) -> Path`
    - Implementasi method `_calculate_rate(text, target_duration) -> str` yang mengembalikan format `[+-]\d+%`
    - Implementasi trim audio jika terlalu panjang, pad silence jika terlalu pendek
    - Gabungkan semua segmen audio dengan silence gaps sesuai timestamp asli
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 7.2 Write property test: TTS Rate Calculation Format
    - **Property 7: TTS Rate Calculation Format**
    - Untuk setiap teks valid dan durasi target positif, `_calculate_rate` mengembalikan string matching pattern `[+-]\d+%`
    - **Validates: Requirements 5.2**

  - [ ]* 7.3 Write property test: Segment Gap Calculation
    - **Property 8: Segment Gap Calculation**
    - Untuk daftar segmen terurut non-overlapping, gap silence antara segmen berurutan = `next.start - prev.end` dan non-negatif
    - **Validates: Requirements 5.5**

  - [ ]* 7.4 Write unit tests untuk Speech Synthesizer
    - Test `_calculate_rate` dengan contoh spesifik (teks pendek/panjang, durasi target berbeda)
    - Test trim dan padding logic (mock edge-tts)
    - Test penggabungan segmen audio dengan gap yang benar
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 8. Implementasi Subtitle Generator
  - [x] 8.1 Buat `src/subtitle_generator.py`
    - Implementasi class `SubtitleGenerator` dengan `MAX_LINE_LENGTH = 42`
    - Implementasi method `generate(segments, output_path) -> Path` yang membuat file SRT
    - Implementasi method `_wrap_text(text) -> str` untuk memecah baris >42 karakter
    - Implementasi method `format_srt(segments) -> str` untuk format string SRT
    - Implementasi static method `parse_srt(srt_content) -> list[TranslatedSegment]`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 8.2 Write property test: SRT Round-Trip
    - **Property 9: SRT Round-Trip**
    - Format segmen ke SRT → parse → format ulang → parse lagi menghasilkan objek subtitle ekuivalen
    - **Validates: Requirements 6.1, 6.2, 6.4**

  - [ ]* 8.3 Write property test: Subtitle Line Wrapping
    - **Property 10: Subtitle Line Wrapping**
    - Setelah `_wrap_text`, setiap baris ≤42 karakter dan semua kata dari teks asli tetap ada
    - **Validates: Requirements 6.3**

  - [ ]* 8.4 Write unit tests untuk Subtitle Generator
    - Test format SRT dengan contoh segmen spesifik
    - Test `_wrap_text` dengan teks pendek dan panjang
    - Test `parse_srt` dengan string SRT valid
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 9. Checkpoint - Pastikan semua test lulus
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implementasi Video Merger
  - [x] 10.1 Buat `src/video_merger.py`
    - Implementasi class `VideoMerger` dengan method `merge(video_path, audio_path, subtitle_path, output_path) -> Path`
    - Gunakan FFmpeg untuk menggabungkan video asli + audio baru + subtitle burn-in
    - Output format: MP4 H.264/AAC
    - Raise `VideoMergeError` jika proses gagal
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 10.2 Write unit tests untuk Video Merger
    - Test FFmpeg command construction (verifikasi flag H.264, AAC, subtitle filter)
    - Test error handling ketika FFmpeg gagal (mock subprocess)
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 11. Implementasi Drive Manager
  - [x] 11.1 Buat `src/drive_manager.py`
    - Implementasi class `DriveManager` dengan `__init__(credentials_path, folder_id)`
    - Implementasi method `download(drive_url, output_path) -> Path`
    - Implementasi method `upload(file_path) -> str` yang mengembalikan shareable link
    - Implementasi static method `extract_file_id(url) -> str | None`
    - Implementasi static method `is_drive_url(text) -> bool`
    - Handle errors: `DriveDownloadError`, `DriveUploadError`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 11.2 Write property test: Google Drive URL Parsing
    - **Property 13: Google Drive URL Parsing**
    - Untuk setiap file ID alfanumerik, konstruksi URL Google Drive lalu `extract_file_id` mengembalikan file ID asli
    - **Validates: Requirements 9.5**

  - [ ]* 11.3 Write unit tests untuk Drive Manager
    - Test `extract_file_id` dengan kedua format URL
    - Test `is_drive_url` dengan URL valid dan invalid
    - Test download dan upload dengan mock Google API client
    - Test error handling: auth failure, file not found
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 12. Implementasi Pipeline Processor
  - [x] 12.1 Buat `src/pipeline.py`
    - Implementasi class `PipelineProcessor` dengan `__init__(work_dir, progress_callback)`
    - Implementasi async method `process(video_path) -> Path` yang menjalankan semua tahap secara berurutan
    - Implementasi method `cleanup()` untuk menghapus file sementara (dipanggil di blok `finally`)
    - Implementasi progress reporting ke callback di setiap tahap
    - Wrap pipeline dengan `asyncio.wait_for()` timeout 30 menit
    - Tangkap exception per-stage dan bungkus dalam `PipelineError` dengan informasi stage
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 8.3, 8.4_

  - [ ]* 12.2 Write property test: Error Message Stage Inclusion
    - **Property 12: Error Message Stage Inclusion**
    - Untuk setiap `PipelineStage` dan pesan error, pesan error user-facing mengandung nama tahap pipeline
    - **Validates: Requirements 8.4**

  - [ ]* 12.3 Write property test: File Size Delivery Routing
    - **Property 11: File Size Delivery Routing**
    - Untuk setiap ukuran file non-negatif, routing memilih "direct Telegram send" jika ≤50MB, "Google Drive upload" jika >50MB
    - **Validates: Requirements 8.1, 8.2**

  - [ ]* 12.4 Write unit tests untuk Pipeline Processor
    - Test urutan eksekusi pipeline (mock semua modul)
    - Test cleanup dipanggil saat sukses dan saat gagal
    - Test timeout handling
    - Test progress callback dipanggil di setiap tahap
    - _Requirements: 10.1, 10.2, 10.3, 10.5_

- [x] 13. Implementasi Telegram Bot
  - [x] 13.1 Buat `src/bot.py`
    - Implementasi class `TelegramBotHandler`
    - Implementasi async handler `handle_video(update, context)` untuk menerima video file
    - Implementasi async handler `handle_document(update, context)` untuk menerima video sebagai document
    - Implementasi async handler `handle_message(update, context)` untuk cek Google Drive link atau tampilkan panduan
    - Implementasi async method `send_progress(chat_id, stage)` untuk kirim status progres
    - Implementasi async method `send_result(chat_id, video_path)` dengan routing: langsung kirim jika ≤50MB, upload ke Drive jika >50MB
    - Implementasi async method `send_error(chat_id, error_message)` untuk kirim pesan error
    - Jalankan pipeline di thread terpisah agar tidak blocking event loop
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 8.4_

  - [x] 13.2 Buat `src/main.py` sebagai entry point
    - Setup `Application` dari `python-telegram-bot`
    - Register semua handlers (video, document, message)
    - Load konfigurasi dari environment variables
    - Jalankan bot dengan `application.run_polling()`
    - _Requirements: 1.1_

  - [ ]* 13.3 Write unit tests untuk Telegram Bot handlers
    - Test `handle_video` dengan mock Update yang berisi video
    - Test `handle_document` dengan mock Update yang berisi document video
    - Test `handle_message` dengan Google Drive link valid
    - Test `handle_message` dengan pesan tanpa video (panduan penggunaan)
    - Test `send_result` routing berdasarkan ukuran file
    - Test `send_error` format pesan error
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 8.4_

- [x] 14. Integrasi dan wiring
  - [x] 14.1 Buat shared test fixtures (`tests/conftest.py`)
    - Buat fixture untuk sample `Segment` dan `TranslatedSegment`
    - Buat fixture untuk `AppConfig` test
    - Buat fixture untuk temporary directory management
    - _Requirements: 3.2, 4.2_

  - [ ]* 14.2 Write integration tests untuk pipeline end-to-end
    - Test pipeline lengkap dengan mock semua external services (FFmpeg, faster-whisper, GoogleTranslator, edge-tts)
    - Test pipeline error handling: gagal di setiap tahap
    - Test Telegram Bot handler flow dari input hingga output
    - _Requirements: 10.1, 10.2, 10.3, 8.3, 8.4_

- [x] 15. Final checkpoint - Pastikan semua test lulus
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Task yang ditandai `*` bersifat opsional dan dapat dilewati untuk MVP lebih cepat
- Setiap task mereferensikan requirements spesifik untuk traceability
- Checkpoint memastikan validasi inkremental di setiap tahap
- Property tests memvalidasi 13 correctness properties dari design document menggunakan Hypothesis
- Unit tests memvalidasi contoh spesifik dan edge cases
- Semua kode ditulis dalam Python sesuai design document
