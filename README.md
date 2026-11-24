# API Peminjaman Alat Laboratorium (Serverless)

Proyek individu mata kuliah Cloud Computing, Week 12: perancangan arsitektur
dan konfigurasi awal infrastruktur di AWS Learner Lab.

Layanan ini mencatat peminjaman alat laboratorium. Setiap data peminjaman
menyimpan nama alat, identitas peminjam, tanggal pinjam, batas pengembalian,
dan status. Implementasi memakai **Track C (Serverless)**:
API Gateway (HTTP API) → AWS Lambda (Python 3.12) → Amazon DynamoDB.

## Struktur repositori

```
.
├── src/handler.py            Fungsi Lambda (routing + operasi CRUD)
├── tests/test_handler.py     Uji unit lokal dengan DynamoDB tiruan (moto)
├── scripts/
│   ├── deploy.sh             Membuat tabel, fungsi, dan API via AWS CLI
│   ├── smoke_test.sh         Uji end-to-end, output disimpan di evidence/
│   └── cleanup.sh            Menghapus semua resource setelah selesai
├── docs/
│   ├── deployment-plan.md    Rencana deployment dan daftar bukti
│   └── arsitektur/           Sumber LaTeX diagram arsitektur
└── requirements-dev.txt
```

## Entitas data: `Loan`

| Atribut         | Tipe   | Keterangan                                   |
|-----------------|--------|----------------------------------------------|
| `loanId`        | String | Partition key, UUID dibuat oleh server       |
| `equipmentName` | String | Nama alat yang dipinjam                      |
| `borrowerName`  | String | Nama peminjam                                |
| `borrowerId`    | String | NIU/NIM peminjam                             |
| `loanDate`      | String | Tanggal pinjam, format `YYYY-MM-DD`          |
| `dueDate`       | String | Batas pengembalian, tidak boleh < `loanDate` |
| `status`        | String | `DIPINJAM`, `DIKEMBALIKAN`, atau `TERLAMBAT` |
| `createdAt`     | String | Waktu dibuat (ISO 8601, UTC)                 |
| `updatedAt`     | String | Waktu terakhir diubah (ISO 8601, UTC)        |

## Endpoint

| Operasi | Method & path            | Respons sukses |
|---------|--------------------------|----------------|
| Create  | `POST /loans`            | `201` + data   |
| Read    | `GET /loans/{loanId}`    | `200` + data   |
| Update  | `PUT /loans/{loanId}`    | `200` + data   |
| Delete  | `DELETE /loans/{loanId}` | `204`          |

Tambahan: `GET /loans` mengembalikan daftar peminjaman (maksimal 100 item).
Kesalahan validasi menghasilkan `400`, ID yang tidak ditemukan `404`.

Contoh request:

```bash
curl -X POST "$API_URL/loans" -H 'Content-Type: application/json' -d '{
  "equipmentName": "Osiloskop Rigol DS1054Z",
  "borrowerName": "Budi Santoso",
  "borrowerId": "512345",
  "loanDate": "2026-11-24",
  "dueDate": "2026-11-27"
}'
```

## Menjalankan uji lokal

Tidak membutuhkan akun AWS dan tidak memakai kredit.

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Deploy ke AWS Learner Lab

1. Buka Learner Lab, klik **Start Lab**, tunggu indikator berwarna hijau.
2. Buka AWS Console, pastikan region **us-east-1 (N. Virginia)**.
3. Buka **CloudShell**, lalu clone repo ini.
4. Jalankan:

```bash
bash scripts/deploy.sh       # membuat DynamoDB, Lambda, API Gateway
bash scripts/smoke_test.sh   # menguji seluruh endpoint
```

Langkah manual lewat Console serta daftar screenshot yang perlu diambil
ada di [`docs/deployment-plan.md`](docs/deployment-plan.md).

Setelah bukti tersimpan dan tidak ada pengujian lagi, jalankan
`bash scripts/cleanup.sh` agar tidak ada resource yang tertinggal.

## Catatan Learner Lab

- Learner Lab tidak mengizinkan pembuatan IAM role. Lambda memakai role
  bawaan `LabRole`.
- Tabel DynamoDB memakai mode on-demand sehingga biaya hanya timbul saat ada
  request. Untuk skala pengujian tugas ini biayanya mendekati nol.
- API belum memakai autentikasi. Ini disengaja untuk tahap prototipe dan
  dicatat sebagai pengembangan berikutnya.
