import os
import psycopg2
import json
import getpass
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class ECLIBatchExporter:
    def __init__(self, db_config):
        self.conn = psycopg2.connect(**db_config)
        
    def export_recent_supreme_court(self, limit=25):
        """Export recent STJ/STA decisions - highest value targets"""
        query = """
        SELECT ecli, court_code, year, relator, area_tematica, meio_processual, 
               decisao, sumario_texto, decisao_integral_texto, descritores
        FROM ecli_documents 
        WHERE court_code IN ('STJ', 'STA')
          AND year >= 2022
          AND sumario_exists = TRUE
          AND LENGTH(sumario_texto) > 200
        ORDER BY 
          CASE WHEN court_code = 'STJ' THEN 1 ELSE 2 END,
          year DESC, 
          LENGTH(decisao_integral_texto) DESC NULLS LAST
        LIMIT %s
        """
        return self._execute_and_format(query, (limit,), "Recent_Supreme_Court")
    
    def export_complex_cases(self, min_length=20000, limit=20):
        """Export longest/most complex decisions with full text"""
        query = """
        SELECT ecli, court_code, year, relator, area_tematica, meio_processual,
               decisao, sumario_texto, decisao_integral_texto, descritores
        FROM ecli_documents 
        WHERE decisao_integral_exists = TRUE
          AND LENGTH(decisao_integral_texto) > %s
          AND year >= 2020
        ORDER BY LENGTH(decisao_integral_texto) DESC
        LIMIT %s
        """
        return self._execute_and_format(query, (min_length, limit), "Complex_Cases")
    
    def export_by_legal_area(self, area, limit=30):
        """Export documents from specific legal area"""
        query = """
        SELECT ecli, court_code, year, relator, area_tematica, meio_processual,
               decisao, sumario_texto, decisao_integral_texto, descritores
        FROM ecli_documents 
        WHERE area_tematica ILIKE %s
          AND year >= 2020
          AND sumario_exists = TRUE
        ORDER BY 
          CASE WHEN court_code = 'STJ' THEN 1 
               WHEN court_code = 'STA' THEN 2 
               ELSE 3 END,
          year DESC
        LIMIT %s
        """
        return self._execute_and_format(query, (f'%{area}%', limit), f"Legal_Area_{area}")
    
    def export_by_outcome(self, outcome_pattern, limit=25):
        """Export cases with specific outcomes"""
        query = """
        SELECT ecli, court_code, year, relator, area_tematica, meio_processual,
               decisao, sumario_texto, decisao_integral_texto, descritores
        FROM ecli_documents 
        WHERE decisao ILIKE %s
          AND year >= 2021
          AND sumario_exists = TRUE
        ORDER BY year DESC
        LIMIT %s
        """
        return self._execute_and_format(query, (f'%{outcome_pattern}%', limit), f"Outcome_{outcome_pattern}")
    
    def export_prolific_judges(self, min_cases=50, limit=30):
        """Export cases from most prolific judges"""
        query = """
        SELECT ecli, court_code, year, relator, area_tematica, meio_processual,
               decisao, sumario_texto, decisao_integral_texto, descritores
        FROM ecli_documents 
        WHERE relator IN (
            SELECT relator 
            FROM ecli_documents 
            WHERE relator IS NOT NULL 
              AND LENGTH(relator) > 3
            GROUP BY relator 
            HAVING COUNT(*) > %s
            ORDER BY COUNT(*) DESC 
            LIMIT 5
        )
        AND year >= 2020
        AND sumario_exists = TRUE
        ORDER BY relator, year DESC
        LIMIT %s
        """
        return self._execute_and_format(query, (min_cases, limit), "Prolific_Judges")
    
    def export_cross_court_comparison(self, legal_concept, limit=25):
        """Export same legal issues across different courts"""
        query = """
        SELECT ecli, court_code, year, relator, area_tematica, meio_processual,
               decisao, sumario_texto, decisao_integral_texto, descritores
        FROM ecli_documents 
        WHERE (sumario_texto ILIKE %s OR descritores ILIKE %s)
          AND year >= 2020
          AND court_code IN ('STJ', 'TRP', 'TRL', 'STA')
        ORDER BY court_code, year DESC
        LIMIT %s
        """
        pattern = f'%{legal_concept}%'
        return self._execute_and_format(query, (pattern, pattern, limit), f"Cross_Court_{legal_concept}")
    
    def _execute_and_format(self, query, params, batch_name):
        """Execute query and format as markdown"""
        cur = self.conn.cursor()
        cur.execute(query, params)
        results = cur.fetchall()
        cur.close()
        
        if not results:
            return f"# No results found for {batch_name}\n"
        
        markdown = self._format_markdown(results, batch_name)
        return markdown
    
    def _format_markdown(self, results, batch_name):
        """Format query results as copy-paste ready markdown"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        
        markdown = f"""# ECLI Metadata Extraction - {batch_name}
**Batch ID:** {batch_name}_{timestamp}
**Documents:** {len(results)}
**Extraction Target:** Conceitos jurídicos, citações legais, precedentes, padrões de decisão

---

Analise estes acórdãos portugueses e extraia metadados estruturados em JSON:

Para cada documento extrair:
• **Conceitos jurídicos principais** (máximo 8)
• **Citações legais** (leis, códigos, decretos, regulamentos)
• **Jurisprudência citada** (outros acórdãos/precedentes)
• **Padrão de decisão** (favorável a quem e argumentos-chave)
• **Complexidade jurídica** (1-10)
• **Domínio legal específico** (mais granular que área temática)
• **Questões de direito principais**
• **Termos técnicos relevantes**

Responder APENAS JSON válido:

---

"""
        
        for i, row in enumerate(results, 1):
            ecli, court_code, year, relator, area_tematica, meio_processual, decisao, sumario_texto, decisao_integral_texto, descritores = row
            
            # Clean and truncate text fields
            sumario = (sumario_texto or "").strip()[:2000]
            decisao_text = (decisao_integral_texto or "").strip()[:30000]  # Max ~25k tokens
            descritores_clean = (descritores or "").strip()
            
            markdown += f"""## DOC_{i:03d}
**ECLI:** {ecli}  
**Tribunal:** {court_code} | **Ano:** {year} | **Relator:** {relator or 'N/A'}  
**Área:** {area_tematica or 'N/A'} | **Meio:** {meio_processual or 'N/A'}  
**Decisão:** {decisao or 'N/A'}  
**Descritores:** {descritores_clean[:200]}...

### Sumário
{sumario}

"""
            if decisao_text and len(decisao_text) > 100:
                markdown += f"""### Decisão Integral
{decisao_text}

"""
            
            markdown += "---\n\n"
        
        # Add JSON format reminder at the end
        markdown += f"""
**FORMATO DE RESPOSTA ESPERADO:**
```json
{{
  "DOC_001": {{
    "ecli": "{results[0][0]}",
    "conceitos_juridicos": ["conceito1", "conceito2"],
    "citacoes_legais": [{{"tipo": "codigo", "ref": "CC art.483", "contexto": "responsabilidade"}}],
    "precedentes": ["ECLI:PT:STJ:2023:...", "Acórdão X"],
    "outcome": "favoravel_requerente",
    "argumentos_chave": ["argumento1", "argumento2"],
    "complexidade": 7,
    "dominio_especifico": "resp_civil_extracontratual",
    "questoes_direito": ["questao1", "questao2"],
    "termos_tecnicos": ["termo1", "termo2"]
  }}
}}
```
"""
        
        return markdown
    
    def save_to_file(self, content, filename):
        """Save markdown content to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        full_filename = f"{filename}_{timestamp}.md"
        
        with open(full_filename, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Exported to: {full_filename}")
        print(f"Characters: {len(content):,}")
        print(f"Ready to copy-paste into Google AI Studio!")
        
        return full_filename

# Usage Examples
if __name__ == "__main__":
    # Database configuration from environment variables
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'ecli_rag_db'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD') or getpass.getpass(prompt='Enter PostgreSQL password: '),
        'port': int(os.getenv('DB_PORT', 5432))
    }
    
    exporter = ECLIBatchExporter(db_config)
    
    # Export different batches for comprehensive testing
    print("=== ECLI Batch Export for Google AI Studio ===\n")
    
    # Batch 1: Recent Supreme Court cases (highest priority)
    print("1. Exporting recent Supreme Court decisions...")
    batch1 = exporter.export_recent_supreme_court(limit=25)
    exporter.save_to_file(batch1, "batch_01_supreme_recent")
    
    # Batch 2: Most complex cases with full decisions
    print("\n2. Exporting complex cases with full decisions...")
    batch2 = exporter.export_complex_cases(min_length=15000, limit=20)
    exporter.save_to_file(batch2, "batch_02_complex_cases")
    
    # Batch 3: Specific legal area (civil procedure)
    print("\n3. Exporting civil procedure cases...")
    batch3 = exporter.export_by_legal_area("proc civ", limit=30)
    exporter.save_to_file(batch3, "batch_03_civil_procedure")
    
    # Batch 4: Favorable outcomes analysis
    print("\n4. Exporting favorable outcomes...")
    batch4 = exporter.export_by_outcome("provido", limit=25)
    exporter.save_to_file(batch4, "batch_04_favorable_outcomes")
    
    # Batch 5: Cross-court comparison on contracts
    print("\n5. Exporting contract law across courts...")
    batch5 = exporter.export_cross_court_comparison("contrato", limit=25)
    exporter.save_to_file(batch5, "batch_05_contracts_cross_court")
    
    print(f"\n✅ Export complete! 5 batches ready for Google AI Studio processing.")
    print("📋 Copy-paste each .md file into AI Studio for metadata extraction.")
    print("🔄 Process results and iterate on different document selections.")