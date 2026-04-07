# -*- coding: utf-8 -*-
import os
import time
import tempfile
import logging
from datetime import datetime

from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Size for disk I/O test (10 MB)
DISK_TEST_SIZE = 10 * 1024 * 1024
# Number of rows for database benchmark
DB_BENCH_ROWS = 1000
# Number of network ping attempts
NETWORK_PING_COUNT = 5


class ServerBenchmark(models.TransientModel):
    _name = 'myschool.server.benchmark'
    _description = 'Server Performance Benchmark'

    target_url = fields.Char(
        string='Target Server URL',
        help='Optional: URL of another MySchool server to test network connectivity '
             '(e.g. https://other-server.example.com)',
    )
    result_summary = fields.Text(string='Results', readonly=True)

    def action_run_benchmark(self):
        self.ensure_one()
        sections = []

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db_name = self.env.cr.dbname
        sections.append(
            f"{'=' * 55}\n"
            f"  SERVER PERFORMANCE BENCHMARK\n"
            f"  Database: {db_name} | {now}\n"
            f"{'=' * 55}"
        )

        for name, method in [
            ('DATABASE', self._benchmark_database),
            ('CPU', self._benchmark_cpu),
            ('MEMORY', self._benchmark_memory),
            ('DISK I/O', self._benchmark_disk_io),
            ('ORM PERFORMANCE', self._benchmark_orm),
        ]:
            try:
                result = method()
                sections.append(f"-- {name} {'-' * (50 - len(name))}\n{result}")
            except Exception as e:
                _logger.exception("Benchmark %s failed", name)
                sections.append(f"-- {name} {'-' * (50 - len(name))}\n  Error: {e}")

        if self.target_url:
            try:
                result = self._benchmark_network()
                sections.append(f"-- NETWORK {'-' * 43}\n{result}")
            except Exception as e:
                _logger.exception("Network benchmark failed")
                sections.append(f"-- NETWORK {'-' * 43}\n  Error: {e}")

        self.result_summary = "\n\n".join(sections)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # DATABASE BENCHMARK
    # ------------------------------------------------------------------

    def _benchmark_database(self):
        cr = self.env.cr
        lines = []

        cr.execute("""
            CREATE TEMP TABLE IF NOT EXISTS _benchmark_test (
                id SERIAL PRIMARY KEY, value TEXT, num INTEGER
            )
        """)
        cr.execute("TRUNCATE _benchmark_test")

        # INSERT
        values = [(f'test_value_{i}', i) for i in range(DB_BENCH_ROWS)]
        start = time.perf_counter()
        cr.executemany(
            "INSERT INTO _benchmark_test (value, num) VALUES (%s, %s)", values,
        )
        elapsed = (time.perf_counter() - start) * 1000
        rate = DB_BENCH_ROWS / (elapsed / 1000) if elapsed > 0 else 0
        lines.append(f"  INSERT  {DB_BENCH_ROWS} rows: {elapsed:>10.1f} ms  ({rate:,.0f} rows/sec)")

        # SELECT
        start = time.perf_counter()
        cr.execute("SELECT id, value, num FROM _benchmark_test")
        rows = cr.fetchall()
        elapsed = (time.perf_counter() - start) * 1000
        rate = len(rows) / (elapsed / 1000) if elapsed > 0 else 0
        lines.append(f"  SELECT  {len(rows)} rows: {elapsed:>10.1f} ms  ({rate:,.0f} rows/sec)")

        # UPDATE
        start = time.perf_counter()
        cr.execute("UPDATE _benchmark_test SET value = 'updated', num = num + 1")
        elapsed = (time.perf_counter() - start) * 1000
        rate = DB_BENCH_ROWS / (elapsed / 1000) if elapsed > 0 else 0
        lines.append(f"  UPDATE  {DB_BENCH_ROWS} rows: {elapsed:>10.1f} ms  ({rate:,.0f} rows/sec)")

        # DELETE
        start = time.perf_counter()
        cr.execute("DELETE FROM _benchmark_test")
        elapsed = (time.perf_counter() - start) * 1000
        rate = DB_BENCH_ROWS / (elapsed / 1000) if elapsed > 0 else 0
        lines.append(f"  DELETE  {DB_BENCH_ROWS} rows: {elapsed:>10.1f} ms  ({rate:,.0f} rows/sec)")

        cr.execute("DROP TABLE IF EXISTS _benchmark_test")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # CPU BENCHMARK
    # ------------------------------------------------------------------

    def _benchmark_cpu(self):
        lines = []
        try:
            load1, load5, load15 = os.getloadavg()
            lines.append(f"  Load average:  {load1:.2f} / {load5:.2f} / {load15:.2f}  (1/5/15 min)")
        except OSError:
            lines.append("  Load average:  not available")

        cpu_count = os.cpu_count() or '?'
        lines.append(f"  CPU cores:     {cpu_count}")

        if HAS_PSUTIL:
            cpu_pct = psutil.cpu_percent(interval=0.5)
            lines.append(f"  CPU usage:     {cpu_pct:.1f}%")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # MEMORY BENCHMARK
    # ------------------------------------------------------------------

    def _benchmark_memory(self):
        lines = []
        if HAS_PSUTIL:
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024 ** 3)
            used_gb = mem.used / (1024 ** 3)
            available_gb = mem.available / (1024 ** 3)
            lines.append(f"  Used:      {used_gb:.1f} GB / {total_gb:.1f} GB  ({mem.percent:.1f}%)")
            lines.append(f"  Available: {available_gb:.1f} GB")

            swap = psutil.swap_memory()
            if swap.total > 0:
                swap_total_gb = swap.total / (1024 ** 3)
                swap_used_gb = swap.used / (1024 ** 3)
                lines.append(f"  Swap:      {swap_used_gb:.1f} GB / {swap_total_gb:.1f} GB  ({swap.percent:.1f}%)")
        else:
            # Fallback: read /proc/meminfo (Linux)
            try:
                with open('/proc/meminfo', 'r') as f:
                    meminfo = {}
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            meminfo[parts[0].rstrip(':')] = int(parts[1])
                total_gb = meminfo.get('MemTotal', 0) / (1024 ** 2)
                available_gb = meminfo.get('MemAvailable', 0) / (1024 ** 2)
                used_gb = total_gb - available_gb
                pct = (used_gb / total_gb * 100) if total_gb > 0 else 0
                lines.append(f"  Used:      {used_gb:.1f} GB / {total_gb:.1f} GB  ({pct:.1f}%)")
                lines.append(f"  Available: {available_gb:.1f} GB")
            except (IOError, KeyError):
                lines.append("  Memory info not available (install psutil for full support)")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # DISK I/O BENCHMARK
    # ------------------------------------------------------------------

    def _benchmark_disk_io(self):
        lines = []
        test_data = os.urandom(DISK_TEST_SIZE)
        size_mb = DISK_TEST_SIZE // (1024 ** 2)

        # Write test
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            start = time.perf_counter()
            tmp.write(test_data)
            tmp.flush()
            os.fsync(tmp.fileno())
            elapsed = time.perf_counter() - start

        write_mbps = size_mb / elapsed if elapsed > 0 else 0
        lines.append(f"  Write {size_mb} MB:  {write_mbps:>8.1f} MB/s")

        # Read test
        start = time.perf_counter()
        with open(tmp_path, 'rb') as f:
            _ = f.read()
        elapsed = time.perf_counter() - start

        read_mbps = size_mb / elapsed if elapsed > 0 else 0
        lines.append(f"  Read  {size_mb} MB:  {read_mbps:>8.1f} MB/s")

        os.unlink(tmp_path)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # ORM BENCHMARK
    # ------------------------------------------------------------------

    def _benchmark_orm(self):
        lines = []
        models_to_test = [
            ('myschool.person', 'person'),
            ('myschool.betask', 'betask'),
            ('myschool.org', 'org'),
            ('myschool.proprelation', 'proprelation'),
            ('myschool.role', 'role'),
        ]

        for model_name, label in models_to_test:
            try:
                model = self.env[model_name].sudo()
                start = time.perf_counter()
                count = model.search_count([])
                elapsed = (time.perf_counter() - start) * 1000
                lines.append(f"  {label + ':':18s} {count:>8,} records  search_count: {elapsed:.1f} ms")
            except Exception:
                lines.append(f"  {label + ':':18s} not available")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # NETWORK BENCHMARK
    # ------------------------------------------------------------------

    def _benchmark_network(self):
        import urllib.request
        import urllib.error
        import json

        url = self.target_url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        ping_url = url.rstrip('/') + '/myschool/benchmark/ping'

        lines = [f"  Target: {url}"]
        timings = []
        status_code = None
        server_info = None
        use_base_url = False

        # First attempt: try the /myschool/benchmark/ping endpoint
        for i in range(NETWORK_PING_COUNT):
            target = url if use_base_url else ping_url
            try:
                req = urllib.request.Request(target, method='GET')
                req.add_header('User-Agent', 'MySchool-Benchmark/1.0')
                start = time.perf_counter()
                with urllib.request.urlopen(req, timeout=10) as resp:
                    elapsed = (time.perf_counter() - start) * 1000
                    status_code = resp.status
                    if i == 0 and not use_base_url:
                        try:
                            body = resp.read().decode('utf-8')
                            server_info = json.loads(body)
                        except Exception:
                            pass
                    timings.append(elapsed)
            except urllib.error.HTTPError as e:
                if not use_base_url and i == 0:
                    # Ping endpoint not available, fall back to base URL
                    use_base_url = True
                    lines.append(f"  (ping endpoint not available, using base URL)")
                    try:
                        req = urllib.request.Request(url, method='GET')
                        req.add_header('User-Agent', 'MySchool-Benchmark/1.0')
                        start = time.perf_counter()
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            elapsed = (time.perf_counter() - start) * 1000
                            status_code = resp.status
                            timings.append(elapsed)
                    except Exception as e2:
                        lines.append(f"  Attempt {i + 1}: failed ({e2})")
                else:
                    lines.append(f"  Attempt {i + 1}: HTTP {e.code}")
            except Exception as e:
                lines.append(f"  Attempt {i + 1}: failed ({e})")

        if timings:
            avg_ms = sum(timings) / len(timings)
            min_ms = min(timings)
            max_ms = max(timings)
            lines.append(
                f"  Ping ({len(timings)}x):  avg {avg_ms:.1f} ms  "
                f"min {min_ms:.1f} ms  max {max_ms:.1f} ms"
            )
            if status_code:
                lines.append(f"  Status: {status_code}")
            if server_info:
                lines.append(f"  Remote DB: {server_info.get('database', '?')}")
        else:
            lines.append("  All ping attempts failed")

        return "\n".join(lines)
