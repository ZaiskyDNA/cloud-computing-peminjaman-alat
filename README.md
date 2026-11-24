# API Peminjaman Alat Laboratorium (Cloud VM)

Proyek individu mata kuliah Cloud Computing, Week 12: perancangan arsitektur
dan konfigurasi awal infrastruktur di AWS Academy.

Layanan ini mencatat peminjaman alat laboratorium. Setiap data peminjaman
menyimpan nama alat, identitas peminjam, tanggal pinjam, batas pengembalian,
dan status. Implementasi memakai **Track A (Cloud VM)**:
Amazon EC2 (Flask, Python 3) → Amazon RDS for MySQL, di dalam VPC sendiri.

## Arsitektur singkat

```
Klien ──HTTP:80──▶ EC2 loans-web (subnet publik) ──MySQL:3306──▶ RDS loans-db (subnet privat)
                    └─ security group loans-web-sg        └─ security group loans-db-sg
                       (80 dari internet)                     (3306 hanya dari loans-web-sg)
```

| Komponen         | Konfigurasi                                                        |
|------------------|--------------------------------------------------------------------|
| VPC              | `loans-vpc` 10.0.0.0/16, Internet Gateway `loans-igw`              |
| Subnet publik    | `loans-public-a` 10.0.1.0/24 (us-east-1a), route 0.0.0.0/0 → IGW    |
| Subnet privat    | `loans-private-a` 10.0.11.0/24, `loans-private-b` 10.0.12.0/24     |
| EC2              | `loans-web`, t3.micro, Amazon Linux 2023, instance profile `LabInstanceProfile` (role `LabRole`) |
| RDS              | `loans-db`, MySQL 8.4, db.t3.micro, 20 GB gp2, Single-AZ, tidak publik |

Diagram lengkap: [`docs/arsitektur/diagram-arsitektur.pdf`](docs/arsitektur/diagram-arsitektur.pdf).

## Struktur repositori

```
.
├── app/app.py                Aplikasi Flask (routing + operasi CRUD ke MySQL)
├── tests/test_app.py         Uji unit lokal dengan database tiruan
├── scripts/
│   ├── deploy.sh             Membuat VPC, security group, RDS, dan EC2 via AWS CLI
│   ├── smoke_test.sh         Uji end-to-end, output disimpan di evidence/
│   └── cleanup.sh            Menghapus semua resource setelah selesai
├── docs/
│   ├── deployment-plan.md    Rencana deployment dan daftar bukti
│   └── arsitektur/           Diagram arsitektur (LaTeX + PDF)
├── evidence/                 Output smoke test dari AWS
├── requirements.txt          Dependensi aplikasi (dipasang di EC2)
└── requirements-dev.txt      Dependensi uji lokal
```

## Entitas data: `Loan`

Disimpan pada tabel MySQL `loans` di database `loansdb`.

| Atribut API     | Kolom MySQL      | Tipe          | Keterangan                                   |
|-----------------|------------------|---------------|----------------------------------------------|
| `loanId`        | `loan_id`        | CHAR(36), PK  | UUID dibuat oleh server                      |
| `equipmentName` | `equipment_name` | VARCHAR(100)  | Nama alat yang dipinjam                      |
| `borrowerName`  | `borrower_name`  | VARCHAR(100)  | Nama peminjam                                |
| `borrowerId`    | `borrower_id`    | VARCHAR(20)   | NIU/NIM peminjam                             |
| `loanDate`      | `loan_date`      | DATE          | Tanggal pinjam, format `YYYY-MM-DD`          |
| `dueDate`       | `due_date`       | DATE          | Batas pengembalian, tidak boleh < `loanDate` |
| `status`        | `status`         | ENUM          | `DIPINJAM`, `DIKEMBALIKAN`, atau `TERLAMBAT` |
| `createdAt`     | `created_at`     | DATETIME      | Waktu dibuat (UTC)                           |
| `updatedAt`     | `updated_at`     | DATETIME      | Waktu terakhir diubah (UTC)                  |

## Endpoint

| Operasi | Method & path            | Respons sukses |
|---------|--------------------------|----------------|
| Create  | `POST /loans`            | `201` + data   |
| Read    | `GET /loans/{loanId}`    | `200` + data   |
| Update  | `PUT /loans/{loanId}`    | `200` + data   |
| Delete  | `DELETE /loans/{loanId}` | `204`          |

Tambahan: `GET /loans` mengembalikan daftar peminjaman (maksimal 100 item) dan
`GET /health` memeriksa koneksi ke RDS. Kesalahan validasi menghasilkan `400`,
ID yang tidak ditemukan `404`.

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

Tidak membutuhkan akun AWS maupun MySQL, dan tidak memakai kredit.

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Deploy ke AWS Academy

1. Buka lab AWS Academy, klik **Start Lab**, tunggu sampai status *ready*.
2. Buka AWS Console, pastikan region **us-east-1 (N. Virginia)**.
3. Buka **CloudShell**, lalu clone repo ini.
4. Jalankan:

```bash
bash scripts/deploy.sh       # VPC, security group, RDS MySQL, EC2 (±10 menit)
bash scripts/smoke_test.sh   # menguji seluruh endpoint
```

`deploy.sh` menyimpan ID resource dan password database (dibuat acak) di file
`.state` yang tidak ikut di-commit. Di EC2, kredensial database disimpan di
`/etc/loans.env` (hanya bisa dibaca root) dan dibaca aplikasi lewat systemd.

Langkah manual lewat Console serta daftar screenshot ada di
[`docs/deployment-plan.md`](docs/deployment-plan.md). Setelah bukti tersimpan,
jalankan `bash scripts/cleanup.sh` agar tidak ada resource yang tertinggal.

## Catatan AWS Academy

- Lab tidak mengizinkan pembuatan IAM role. EC2 memakai instance profile
  bawaan `LabInstanceProfile` (role `LabRole`), yang juga memungkinkan akses
  shell lewat Systems Manager Session Manager tanpa membuka port SSH.
- RDS tidak dapat diakses dari internet: berada di subnet privat, opsi
  *publicly accessible* dimatikan, dan port 3306 hanya menerima koneksi dari
  security group EC2.
- Tidak memakai NAT Gateway atau Elastic IP agar biaya tetap rendah.
- API belum memakai HTTPS dan autentikasi. Ini disengaja untuk tahap
  prototipe dan dicatat sebagai pengembangan berikutnya.
