# Text Patterns Analysis

This document contains the font and size information for metadata fields and their content based on the analysis of Portuguese legal documents.

## Font Properties for Metadata Fields

### Metadata Field Labels
- **Font**: "Helvetica-Bold"
- **Size**: 10.0pt
- **Formatting**: Bold
- **Examples**: "Relator", "Nº do Documento", "Apenso", "Data do Acordão", "Votação", "Tribunal de recurso", "Processo de recurso", "Recurso", "Referência de processo de recurso", "Nível de acesso", "Meio Processual", "Decisão", "Indicações eventuais", "Área Temática", "Referências Internacionais", "Jurisprudência Nacional", "Legislação Comunitária", "Legislação Estrangeira", "Descritores"

### Metadata Field Content Values
- **Font**: "Helvetica"
- **Size**: 10.0pt (for most metadata values), 12.0pt (for some main content on page 2)
- **Formatting**: Not bold
- **Examples**: "Arlindo Martins", "sa119531218004153", "18/12/2053", "unanimidade", "Raul Borges", "27/06/2012"

### Special Elements

#### ECLI URL
- **Font**: "Helvetica"
- **Size**: 9.0pt
- **Formatting**: Not bold

#### "Sumário:" Header
- **Font**: "Helvetica-Bold"
- **Size**: 20.5pt
- **Formatting**: Bold

#### "Decisão Integral:" Header
- **Font**: "Helvetica-Bold"
- **Size**: 20.5pt
- **Formatting**: Bold

#### Sumário and Decisão Integral Content
- **Font**: "Helvetica"
- **Size**: 12.0pt
- **Formatting**: Not bold
- **Content Type**: Main content following section headers
- **Examples**: 
  - Sumário: Legal principles and holdings (e.g., "I- No âmbito do processo penal, o art.79.º n.º2 al. d) do RGICSF...")
  - Decisão Integral: Full court decision text (e.g., "Acordam, em conferência, na Secção Criminal deste Tribunal...")

#### Footer Elements
- **Separators**: "Helvetica" at 8.0pt
  - Examples: "|", "─", horizontal lines
- **Timestamps**: "Helvetica" at 7.0pt
  - Examples: "23 228 058 07 05 2020", date/time stamps
- **Page Numbers**: "Helvetica" at 6.0pt
  - Examples: "Página 1 |", page numbering
- **Contact Info**: "Helvetica-Bold" at 6.5pt (bold)
  - Examples: "Rua Duque de Palmela, 23 | 1250-097 Lisboa", "http://www.csm.org.pt | csm@csm.org.pt"
- **TCPDF Footer**: "Helvetica" at 1.0pt
  - Examples: "Powered by TCPDF (www.tcpdf.org)", technical footer text

## Key Observations

1. **Clear Visual Distinction**: Field labels use bold Helvetica at 10.0pt, while content values use regular Helvetica at 10.0pt, establishing a clear visual hierarchy for extraction algorithms.

2. **Consistent Pattern**: This font pattern is consistent across all metadata fields in the analyzed document, making it reliable for automated extraction.

3. **Content Type Classification**: The analysis includes automatic classification of content types (URL, ECLI, date, page number, contact info, address, separator, timestamp, metadata field, header, footer, main content).

4. **Positioning Data**: Each text span includes bounding box coordinates and dimensions for precise location-based extraction.

## Usage for Extraction Algorithms

This information can be used to:
- Identify metadata field labels by looking for "Helvetica-Bold" at 10.0pt
- Extract corresponding values by finding "Helvetica" at 10.0pt in proximity to field labels
- Distinguish between different document sections based on font properties
- Implement robust content classification based on font characteristics