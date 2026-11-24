# Rencana Deployment

Dokumen ini menjelaskan urutan pembuatan resource Track A (EC2 + RDS MySQL)
di AWS Academy, cara memverifikasinya, dan bukti yang dikumpulkan pada Week 12.

## 1. Lingkungan

| Komponen        | Nilai                                                          |
|-----------------|----------------------------------------------------------------|
| Akun            | AWS Academy (Sandbox Environment, AWS Academy Cloud Foundations) |
| Region          | `us-east-1` (N. Virginia)                                      |
| VPC             | `loans-vpc`, 10.0.0.0/16, DNS hostnames aktif                  |
| Subnet publik   | `loans-public-a` 10.0.1.0/24, us-east-1a, auto-assign IP publik |
| Subnet privat   | `loans-private-a` 10.0.11.0/24 (1a), `loans-private-b` 10.0.12.0/24 (1b) |
| Routing         | `loans-public-rt`: 0.0.0.0/0 → `loans-igw`; subnet privat memakai main route table (lokal saja) |
| Security group  | `loans-web-sg`: TCP 80 dari 0.0.0.0/0; `loans-db-sg`: TCP 3306 hanya dari `loans-web-sg` |
| RDS             | `loans-db`, MySQL 8.4, db.t3.micro, 20 GB gp2, Single-AZ, tidak publik, database `loansdb` |
| EC2             | `loans-web`, t3.micro, Amazon Linux 2023, `LabInstanceProfile` (role `LabRole`) |
| Aplikasi        | Flask + PyMySQL, layanan systemd `loans`, port 80             |

## 2. Urutan deployment

Resource dibuat dari lapisan jaringan ke lapisan data lalu lapisan aplikasi,
sehingga setiap lapisan bisa diverifikasi sebelum lapisan berikutnya dibuat.

**Tahap 1 — Jaringan.** Buat VPC, Internet Gateway, satu subnet publik, dua
subnet privat (dua AZ, syarat DB subnet group RDS), dan route table publik.
Verifikasi: *VPC → Resource map* menampilkan 3 subnet, route table, dan IGW.

**Tahap 2 — Security group.** `loans-web-sg` untuk EC2 dan `loans-db-sg` untuk
RDS. Verifikasi: inbound rule `loans-db-sg` hanya berisi port 3306 dengan
sumber `loans-web-sg`.

**Tahap 3 — RDS.** Buat DB subnet group dari dua subnet privat, lalu instance
MySQL `loans-db` dengan *Public access: No*. Password master dibuat acak oleh
skrip. Verifikasi: status *Available*, *Internet access gateway: Disabled*.

**Tahap 4 — EC2.** Luncurkan instance di subnet publik dengan user data yang
memasang Python, Flask, PyMySQL, dan klien MariaDB, menulis `/etc/loans.env`
(endpoint dan kredensial RDS), lalu menjalankan layanan systemd `loans`.
Verifikasi: status *Running*, *3/3 checks passed*, `GET /health` mengembalikan
`"database": "connected"`.

**Tahap 5 — Uji konektivitas.** Jalankan `scripts/smoke_test.sh` dari
CloudShell. Urutan status yang diharapkan: 200 (health), 201, 200, 200, 200,
204, 404. Verifikasi tambahan: masuk ke EC2 lewat Session Manager dan
jalankan query `SELECT` langsung ke RDS.

Tahap 1–4 dijalankan sekaligus dengan `bash scripts/deploy.sh`.

### Alternatif lewat Console

1. **VPC → Create VPC → VPC and more.** Nama `loans`, CIDR 10.0.0.0/16,
   2 AZ, 1 subnet publik dan 2 subnet privat, NAT gateway *None*,
   VPC endpoint *None*.
2. **EC2 → Security Groups.** Buat `loans-web-sg` (inbound HTTP 80 dari
   *Anywhere*) dan `loans-db-sg` (inbound MySQL/Aurora 3306 dengan sumber
   `loans-web-sg`).
3. **RDS → Create database.** *Standard create*, MySQL, template *Free tier*
   / *Dev/Test*, db.t3.micro, 20 GB gp2, VPC `loans-vpc`, *Public access: No*,
   security group `loans-db-sg`, initial database `loansdb`. Hapus centang
   *Enhanced monitoring* (tidak didukung di lab).
4. **EC2 → Launch instance.** Amazon Linux 2023, t3.micro, subnet publik,
   `loans-web-sg`, IAM instance profile `LabInstanceProfile`. Isi *User data*
   dengan bagian user data dari `scripts/deploy.sh` (ganti nilai `DB_HOST` dan
   `DB_PASSWORD`).

## 3. Bukti yang dikumpulkan

| No | Bukti                                                                 | Sumber                          |
|----|-----------------------------------------------------------------------|---------------------------------|
| 1  | Lab aktif (*Lab status: ready*)                                       | Halaman lab AWS Academy         |
| 2  | Resource map VPC: subnet, route table, Internet Gateway               | VPC → Your VPCs → `loans-vpc`   |
| 3  | Inbound rule `loans-db-sg` (3306 hanya dari `loans-web-sg`)           | EC2 → Security Groups           |
| 4  | Output `deploy.sh` termasuk hasil `GET /health`                       | CloudShell                      |
| 5  | RDS `loans-db` *Available*, akses internet *Disabled*                 | RDS → Databases                 |
| 6  | EC2 `loans-web` *Running*, IAM role `LabRole`, VPC dan subnet         | EC2 → Instances                 |
| 7  | Output `smoke_test.sh` (terminal + `evidence/smoke-test-output.txt`)  | CloudShell                      |
| 8  | Data peminjaman dibaca lewat `GET /loans`                             | CloudShell                      |
| 9  | Query MySQL dari EC2 langsung ke RDS                                  | Systems Manager → Session Manager |
| 10 | Riwayat commit repositori                                             | GitHub → Commits                |

## 4. Pengendalian biaya

- Ukuran terkecil yang cukup: EC2 t3.micro dan RDS db.t3.micro Single-AZ,
  penyimpanan 20 GB gp2, tanpa backup otomatis (retensi 0 hari).
- Tidak memakai NAT Gateway, Elastic IP, atau Enhanced Monitoring.
- EC2 dan RDS ditagih per jam selama berjalan. Setelah bukti diambil,
  akhiri sesi lab; setelah proyek dinilai jalankan `scripts/cleanup.sh`.
- Catatan: pada Sandbox Environment AWS Academy, seluruh resource otomatis
  dihapus ketika sesi lab berakhir, sehingga deploy dijalankan ulang dengan
  `deploy.sh` bila diperlukan.

## 5. Rencana minggu berikutnya

- HTTPS lewat Application Load Balancer dan sertifikat ACM, sekaligus
  memindahkan EC2 ke subnet privat.
- Menyimpan kredensial database di AWS Secrets Manager, bukan file env.
- Autentikasi sederhana (API key) dan penandaan status `TERLAMBAT` otomatis.
- Menjalankan aplikasi dengan Gunicorn di belakang Nginx.
