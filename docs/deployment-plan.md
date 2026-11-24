# Rencana Deployment

Dokumen ini menjelaskan urutan pembuatan resource di AWS Learner Lab,
cara memverifikasinya, dan bukti yang dikumpulkan pada Week 12.

## 1. Lingkungan

| Komponen   | Nilai                                         |
|------------|-----------------------------------------------|
| Akun       | AWS Academy Learner Lab                       |
| Region     | `us-east-1` (N. Virginia)                     |
| IAM role   | `LabRole` (bawaan Learner Lab)                |
| Tabel      | `Loans`, partition key `loanId` (String), on-demand |
| Fungsi     | `loans-handler`, Python 3.12, 128 MB, timeout 10 detik |
| API        | `loans-api`, HTTP API, stage `$default` (auto-deploy) |

## 2. Urutan deployment

Resource dibuat dari lapisan data ke lapisan depan, sehingga setiap lapisan
bisa diuji sebelum lapisan berikutnya ditambahkan.

**Tahap 1 — DynamoDB.** Buat tabel `Loans`. Verifikasi status tabel `ACTIVE`.

**Tahap 2 — Lambda.** Unggah `src/handler.py`, set role `LabRole`,
tambahkan environment variable `TABLE_NAME=Loans`. Verifikasi dengan event
uji di tab *Test* (contoh event di bawah). Hasil yang diharapkan:
`statusCode: 201` dan item baru muncul di tabel.

**Tahap 3 — API Gateway.** Buat HTTP API dengan integrasi Lambda
(payload 2.0) dan lima route. Verifikasi dengan `scripts/smoke_test.sh`.

Ketiga tahap dapat dijalankan sekaligus dengan `bash scripts/deploy.sh`.

### Event uji Lambda (tab Test)

```json
{
  "routeKey": "POST /loans",
  "body": "{\"equipmentName\":\"Multimeter Sanwa CD800a\",\"borrowerName\":\"Budi Santoso\",\"borrowerId\":\"512345\",\"loanDate\":\"2026-11-24\",\"dueDate\":\"2026-11-26\"}"
}
```

### Alternatif lewat Console

1. **DynamoDB → Create table.** Nama `Loans`, partition key `loanId` (String).
   Pada *Table settings* pilih *Customize settings*, lalu *On-demand*.
2. **Lambda → Create function.** *Author from scratch*, nama `loans-handler`,
   runtime Python 3.12. Pada *Change default execution role* pilih
   *Use an existing role* → `LabRole`. Tempel isi `src/handler.py` ke editor,
   ubah nama file menjadi `handler.py`, ubah *Handler* menjadi
   `handler.lambda_handler`, lalu *Deploy*. Di *Configuration → Environment
   variables* tambahkan `TABLE_NAME = Loans`.
3. **API Gateway → Create API → HTTP API.** Tambahkan integrasi Lambda
   `loans-handler`, lalu buat route:
   `POST /loans`, `GET /loans`, `GET /loans/{loanId}`,
   `PUT /loans/{loanId}`, `DELETE /loans/{loanId}`.
   Stage `$default` dengan auto-deploy aktif.

## 3. Bukti yang dikumpulkan

| No | Bukti                                                        | Sumber                     |
|----|--------------------------------------------------------------|----------------------------|
| 1  | Learner Lab aktif (indikator hijau) dan sisa kredit          | Halaman Learner Lab        |
| 2  | Tabel `Loans` berstatus Active, partition key `loanId`       | DynamoDB → Tables          |
| 3  | Konfigurasi Lambda: runtime, role `LabRole`, env `TABLE_NAME` | Lambda → Configuration     |
| 4  | Hasil tab *Test* Lambda dengan `statusCode` 201              | Lambda → Test              |
| 5  | Daftar route dan integrasi di API Gateway                    | API Gateway → Routes       |
| 6  | Output `smoke_test.sh` (terminal + `evidence/smoke-test-output.txt`) | CloudShell          |
| 7  | Item hasil POST terlihat di tabel                            | DynamoDB → Explore items   |
| 8  | Log eksekusi Lambda                                          | CloudWatch → Log groups    |

Catatan: ambil screenshot nomor 7 sebelum langkah DELETE pada smoke test,
atau jalankan satu `POST /loans` tambahan setelah smoke test selesai.

## 4. Pengendalian biaya

- DynamoDB on-demand dan Lambda hanya ditagih per request; tidak ada
  resource yang berjalan terus seperti EC2 atau RDS.
- Tidak memakai NAT Gateway, VPC endpoint, atau Elastic IP.
- Retensi log CloudWatch bisa diset 1–3 hari bila diperlukan.
- Setelah proyek selesai dinilai, jalankan `scripts/cleanup.sh`.

## 5. Rencana minggu berikutnya

- Menambahkan autentikasi sederhana (API key lewat Lambda authorizer).
- Menambahkan Global Secondary Index pada `borrowerId` agar daftar
  peminjaman per mahasiswa tidak memakai `Scan`.
- Penandaan status `TERLAMBAT` otomatis memakai EventBridge Scheduler.
