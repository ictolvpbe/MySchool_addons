# LLM Kennisbank voor MySchool — Implementatieplan

## Architectuur: RAG (Retrieval-Augmented Generation)

Documenten worden geindexeerd als vector embeddings. Bij een zoekvraag worden relevante fragmenten opgehaald en meegegeven als context aan de LLM.

## Componenten

### 1. LLM Server — Ollama
- Makkelijkste manier om open-source modellen lokaal te draaien
- `curl -fsSL https://ollama.com/install.sh | sh`
- Modellen: **Llama 3.1 8B** (snel, goed genoeg voor Q&A) of **Mistral 7B**
- REST API op `localhost:11434`
- GPU aanbevolen (NVIDIA met 8GB+ VRAM), maar draait ook op CPU

### 2. Embeddings
- Ollama kan ook embedding-modellen draaien: `nomic-embed-text` of `mxbai-embed-large`
- Alternatief: **sentence-transformers** via een klein Python-script

### 3. Vector Database — pgvector
- Extensie voor PostgreSQL — Odoo draait al op PostgreSQL, dus geen extra infra nodig
- Alternatief: **ChromaDB** (standalone) of **Qdrant**

### 4. Odoo-integratie — OdooBot

Integratie via OdooBot in Discuss. Gebruikers stellen vragen aan @OdooBot en krijgen antwoorden uit de kennisbank.

---

## Module-structuur

```
myschool_knowledge/
├── models/
│   ├── __init__.py
│   ├── knowledge_article.py     # Artikelen beheren
│   ├── knowledge_chunk.py       # Chunks + embeddings
│   └── mail_bot.py              # OdooBot override
├── views/
│   └── knowledge_article_views.xml
├── security/
│   └── ir.model.access.csv
└── __manifest__.py              # depends: ['mail', 'myschool_core']
```

---

## RAG Flow

```
Gebruiker stelt vraag
    |
Query wordt ge-embed via Ollama embeddings API
    |
pgvector zoekt top-K meest relevante chunks (cosine similarity)
    |
Chunks + vraag worden als prompt naar Ollama LLM gestuurd
    |
Antwoord + bronverwijzingen terug naar gebruiker
```

---

## OdooBot Integratie

```python
# models/mail_bot.py

from odoo import models, api
import requests
import json
import threading

_llm_semaphore = threading.Semaphore(2)  # max 2 gelijktijdig


class MailBot(models.AbstractModel):
    _inherit = 'mail.bot'

    def _get_answer(self, record, body, values, command=False):
        """Override: route vragen door de RAG pipeline."""
        answer = self._knowledge_search(body)
        if answer:
            return answer
        return super()._get_answer(record, body, values, command=command)

    def _knowledge_search(self, question):
        """RAG pipeline: embed -> zoek -> genereer antwoord."""
        if not _llm_semaphore.acquire(timeout=30):
            return "Even geduld, ik ben druk bezig met andere vragen."
        try:
            # 1. Embed de vraag
            embed_resp = requests.post('http://localhost:11434/api/embed', json={
                'model': 'nomic-embed-text',
                'input': question,
            }, timeout=10)
            embedding = embed_resp.json()['embeddings'][0]

            # 2. Zoek relevante chunks via pgvector
            self.env.cr.execute("""
                SELECT content, article_id, 1 - (embedding <=> %s::vector) AS score
                FROM knowledge_chunk
                WHERE 1 - (embedding <=> %s::vector) > 0.7
                ORDER BY embedding <=> %s::vector
                LIMIT 5
            """, [str(embedding), str(embedding), str(embedding)])
            chunks = self.env.cr.dictfetchall()

            if not chunks:
                return False

            # 3. Bouw prompt met context
            context = "\n\n".join([c['content'] for c in chunks])
            prompt = f"""Beantwoord de vraag op basis van de volgende context.
Als het antwoord niet in de context staat, zeg dat eerlijk.

Context:
{context}

Vraag: {question}

Antwoord:"""

            # 4. Genereer antwoord via Ollama
            gen_resp = requests.post('http://localhost:11434/api/generate', json={
                'model': 'llama3.1',
                'prompt': prompt,
                'stream': False,
            }, timeout=30)
            answer = gen_resp.json()['response']

            # 5. Voeg bronverwijzingen toe
            article_ids = list(set(c['article_id'] for c in chunks))
            articles = self.env['knowledge.article'].browse(article_ids)
            sources = ", ".join(articles.mapped('name'))

            return f"{answer}\n\nBronnen: {sources}"

        except Exception:
            return False
        finally:
            _llm_semaphore.release()
```

---

## Resourcevereisten

| Component | RAM | CPU | Opslag |
|-----------|-----|-----|--------|
| Llama 3.1 8B (Q4) | ~6 GB | 4-8 cores | ~5 GB |
| Embedding model | ~1 GB | 1-2 cores | ~300 MB |
| Odoo + PostgreSQL | ~2-4 GB | 2-4 cores | variabel |
| **Totaal minimum** | **~12 GB** | **8 cores** | **10 GB** |
| **Aanbevolen** | **16-24 GB** | **12+ cores** | **20 GB** |

## Belasting per operatie

| Operatie | Belasting | Duur |
|----------|-----------|------|
| Antwoord genereren (inferentie) | ZWAAR — alle CPU-cores 100% | 5-15s per antwoord (CPU) |
| Embeddings genereren | Middelmatig | ~0.5s per chunk |
| Vector search (pgvector) | Licht — SQL query | <0.1s |

### Tijdlijn van een vraag

```
[0.0s] Vraag ontvangen           -> niks
[0.1s] Query embedden            -> licht  (CPU ~20% voor ~0.5s)
[0.2s] pgvector zoeken           -> minimaal
[0.3s] Prompt naar LLM sturen    -> ZWAAR (CPU 100%, 5-15s)
[~10s] Antwoord klaar            -> niks
```

## CPU vs GPU vergelijking

| | CPU (12 cores) | GPU (RTX 3060) |
|---|---|---|
| Snelheid | 3-8 tok/s | 30-40 tok/s |
| Antwoordtijd | 5-15s | 1-3s |
| Gelijktijdig | 1-2 vragen | 3-5 vragen |
| Werkbaar? | Ja, voor <20 gebruikers | Comfortabel voor 50+ |

---

## Proxmox VM Setup

### VM-instellingen

| Instelling | Waarde |
|---|---|
| OS | Debian 13 |
| CPU | 8-12 cores, **type: host** (cruciaal voor AVX2) |
| RAM | 16-24 GB, **geen ballooning** |
| Disk | 30 GB+ (SSD/NVMe sterk aanbevolen) |
| Network | vmbr0, standaard |

**CPU type "host"** is cruciaal — zonder dit geen AVX2/AVX-512 en draait Ollama 2-3x trager.

### Optioneel: GPU passthrough

```bash
# Op de Proxmox host — IOMMU inschakelen
# /etc/default/grub
GRUB_CMDLINE_LINUX_DEFAULT="quiet intel_iommu=on iommu=pt"
# of voor AMD:
GRUB_CMDLINE_LINUX_DEFAULT="quiet amd_iommu=on iommu=pt"
```

Dan in Proxmox UI: VM -> Hardware -> Add -> PCI Device -> selecteer de GPU.

### Proxmox-specifieke tips

- Geen KSM (memory sharing) voor deze VM
- CPU pinning via taskset als andere VM's beschermd moeten worden
- Backup uitsluiten van Ollama modellen (`/usr/share/ollama/.ollama/models`)

### Deployment-opties

**Optie 1: Alles op 1 VM**
```
Debian 13 VM
├── Ollama          -> localhost:11434  (LLM + embeddings)
├── PostgreSQL 17   -> localhost:5432   (Odoo DB + pgvector)
└── Odoo 19         -> :8069           (myschool + knowledge module)
```

**Optie 2: Gescheiden (als Odoo al op een andere VM draait)**
```
VM 1 (bestaand)              VM 2 (nieuw, 16GB RAM)
├── Odoo 19        --HTTP--> ├── Ollama
└── PostgreSQL+pgvector      └── (meer niet)
```

Verander in de module de URL van `localhost:11434` naar het IP van VM 2.

---

## Implementatiestappen

1. Ollama installeren op server + modellen pullen (`ollama pull llama3.1`, `ollama pull nomic-embed-text`)
2. pgvector installeren op PostgreSQL (`CREATE EXTENSION vector;`)
3. `knowledge_article` model maken — kennisdocumenten opslaan
4. Chunking pipeline — bij opslaan: splits in ~500 token stukken, genereer embeddings, sla op met `vector` kolom
5. Zoek-endpoint — embed vraag, `ORDER BY embedding <=> query_embedding LIMIT 5`, stuur naar Ollama
6. OdooBot override — integratie via Discuss
