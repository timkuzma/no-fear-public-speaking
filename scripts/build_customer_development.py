#!/usr/bin/env python3
"""Build the standalone public reader from the user-approved PDF archive.

Run with the bundled Python runtime (pdfplumber is a build-only dependency).
Never copy source PDFs or extraction caches into public/.
"""
import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

ACTION_STARTS = {
    'Дальнейшие шаги', 'Следующие шаги', 'Что стоит проверить дальше',
    'Предлагаемый первый продуктовый тест', 'Предлагаемый первый эксперимент',
    'Что спросить в следующих интервью', 'Решение на текущем этапе',
    'Что стоит проверить в продукте', 'С чего можно начать проверку',
    'Принятые решения',
}
# Stop at these peer sections, not at subheadings inside an action plan.
ACTION_ENDS = {'Расшифровка', 'Ограничения исследования', 'Связь с предыдущим интервью',
               'Связанные материалы', 'Что пока нельзя утверждать'}
INLINE_ACTION = re.compile(r'^(Как проверить|Критерий решения):')
GROUPS = [('ideal', 'Идеальный клиент'), ('other', 'Другие сегменты')]

# These are narrator's research/process notes, never interview answers.
EDITORIAL_SENTENCES = (
    'Курс и уровень обучения в разговоре не уточняли.',
    'Курс и уровень обучения по этому материалу определить не получилось.',
    'В разговоре затронули и неясные ожидания, но эту мысль первым предложил интервьюер.',
    'Так респондент описывает свою трудность; темп речи по аудио здесь не измеряли.',
    'Дополнительная проверка до выступления могла бы пригодиться, но из этого случая ещё не следует, что ИИ справится с ней вместо специалиста.',
    'Но это пока ответ на названную цену, а не покупка.',
    'Как часто это происходит, не выяснили.',
    'Этот опыт усилил ориентацию [R005] на реакцию аудитории, но в интервью не разобран как отдельная проблема, за которую она ищет новый инструмент.',
    'Полная симуляция аудитории, анализ видео и ораторская обратная связь в интервью не запрашивались.',
    'По итогам [третье лицо] склоняется сменить целевой сегмент продукта и договорилась провести ещё один каздев с [третье лицо].',
    'Встречу пришлось прервать из-за проблем со связью.',
)


def clean_editorial_note(block):
    text = block['text']
    # Participant speech and source transcripts are protected by the caller.
    if text.startswith(('Исследование проведено с одной', 'Разбор пока предварительный:',
                        'Про оплату и частоту использования не спрашивали.')):
        return None
    text = re.split(r'\bСигнал (?:сильный|средний|слабый)', text, maxsplit=1)[0].strip()
    for sentence in EDITORIAL_SENTENCES:
        text = text.replace(sentence, '')
    if text.startswith('Ключевое ограничение: '):
        text = text.removeprefix('Ключевое ограничение: ')
        text = text[:1].upper() + text[1:]
    text = re.sub(r' {2,}', ' ', text).strip()
    return dict(block, text=text) if text else None


def apply_conclusions(documents, editorial):
    entries = editorial['documents']
    if set(entries) != {doc['id'] for doc in documents}:
        raise ValueError('Editorial conclusions must cover the archive exactly')
    audit = []
    for doc in documents:
        original = doc['blocks']
        entry = entries[doc['id']]
        if len(entry['findings']) != 4 or not entry['product'].strip():
            raise ValueError(f'Incomplete conclusions: {doc["id"]}')
        evidence = []
        for finding in entry['findings']:
            if not finding['heading'].strip() or not finding['text'].strip() or not finding['evidence']:
                raise ValueError(f'Incomplete finding: {doc["id"]}')
            for anchor in finding['evidence']:
                matches = [i for i, block in enumerate(original) if anchor in block['text']]
                if not matches:
                    raise ValueError(f'Missing source anchor: {doc["id"]}: {anchor}')
                evidence.append({'anchor': anchor, 'source_blocks': matches})
        replacement = [{'type':'h2', 'text':'Основные выводы'}]
        for finding in entry['findings']:
            replacement.extend([{'type':'h3','text':finding['heading']},
                                {'type':'p','text':finding['text']}])
        replacement.extend([{'type':'h3','text':'Значение для продукта'},
                            {'type':'p','text':entry['product']}])
        result = []
        replacing, preserved_subsection, transcript = False, False, False
        replaced = 0
        for block in original:
            if block['type'] == 'h2':
                replacing = block['text'] == 'Основные выводы'
                preserved_subsection = False
                transcript = block['text'] == 'Расшифровка'
                if replacing:
                    result.extend(replacement)
                    replaced += 1
                    continue
            if replacing:
                if block['type'] == 'h3':
                    preserved_subsection = block['text'] == 'Важные цитаты'
                if preserved_subsection:
                    result.append(block)
                continue
            protected = transcript or re.match(
                r'^(?:\d+\. Интервьюер\b|Респондент [RM]\d{3}\b|(?:Интервьюер|Респондент(?: [RM]\d{3})?):)',
                block['text'])
            cleaned = block if protected else clean_editorial_note(block)
            if cleaned:
                result.append(cleaned)
        if replaced != 1:
            raise ValueError(f'Expected one conclusion section: {doc["id"]}')
        doc['blocks'] = result
        audit.append({'id':doc['id'], 'editorial_version':editorial['version'],
                      'source_blocks_sha256':hashlib.sha256(json.dumps(original, ensure_ascii=False).encode()).hexdigest(),
                      'finding_evidence':evidence})
    return audit


def remove_actions(lines):
    retained, removed, active = [], [], None
    inline = False
    for line in lines:
        text = line['text'].strip()
        heading = line['size'] >= 11.5
        if heading and text in ACTION_ENDS:
            active = None
        if heading and text in ACTION_STARTS:
            active = text
            removed.append(text)
        if active:
            continue
        if INLINE_ACTION.match(text):
            inline = True
            removed.append(text.split(':', 1)[0])
        elif heading or re.match(r'^(Гипотеза|Основание|Статус):', text):
            inline = False
        if not inline:
            retained.append(line)
    return retained, removed


def blocks_from_lines(lines):
    blocks, previous = [], None
    transcript = False
    for line in lines:
        text = re.sub(r'\s+', ' ', line['text']).strip()
        if not text:
            continue
        size = line['size']
        kind = 'h1' if size >= 20 else 'h2' if size >= 14 else 'h3' if size >= 11.5 else 'p'
        if kind == 'h2':
            transcript = text == 'Расшифровка'
        speaker = bool(re.match(r'^(?:\d+\. )?(?:Интервьюер|Респондент\b)', text))
        bullet = text.startswith('• ')
        if bullet:
            kind = 'li'
            text = text[2:]
        new_paragraph = previous and line['page'] == previous['page'] and line['top'] - previous['bottom'] > 8
        same_line_style = previous and abs(size - previous['size']) < .1
        # PDF page boundaries are layout, not paragraph boundaries. A new label,
        # list item or speaker still starts a block even without a vertical gap.
        label = bool(re.match(r'^(?:Профиль|Почему выбран|Проблема:|Нужное решение:|Гипотеза:|Основание:|Статус:|H\d\b|\d+\. )', text))
        bold_heading = kind == 'p' and line['bold'] > .97 and not speaker and not label and not transcript
        if bold_heading:
            kind = 'h4'
        continuation = blocks and same_line_style and not new_paragraph and not speaker and not bullet and not label
        if continuation and ((kind in ('p','h4') and blocks[-1]['type'] in ('p','li','h4')) or (kind == blocks[-1]['type'] and kind == 'h3')):
            blocks[-1]['text'] += ' ' + text
        else:
            blocks.append({'type': kind, 'text': text})
        previous = line
    return blocks


def extract_archive(archive):
    import pdfplumber
    documents, audit = [], []
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not name.lower().endswith('.pdf'):
                continue
            parts = Path(name).parts
            group = next((key for key, label in GROUPS if label == parts[-2]), None)
            if group is None:
                raise ValueError(f'Unexpected archive folder: {name}')
            lines = []
            with pdfplumber.open(io.BytesIO(z.read(name))) as pdf:
                for pi, page in enumerate(pdf.pages):
                    for line in page.extract_text_lines():
                        chars = line['chars']
                        size = max(round(c['size'], 1) for c in chars)
                        # Small repeated page footers are not document content.
                        if size < 9 or line['top'] > page.height - 45:
                            continue
                        bold = sum('Semibold' in c['fontname'] or 'Bold' in c['fontname'] for c in chars) / len(chars)
                        lines.append({'text':line['text'], 'size':size, 'bold':bold,
                                      'top':line['top'], 'bottom':line['bottom'], 'page':pi})
            retained, removed = remove_actions(lines)
            blocks = blocks_from_lines(retained)
            # Ensure the formatter preserved every retained character in order,
            # except PDF whitespace and the bullet glyph mapped to a real list.
            normalize = lambda s: re.sub(r'\s|•', '', s)
            assert normalize(''.join(l['text'] for l in retained)) == normalize(''.join(b['text'] for b in blocks)), name
            title = blocks.pop(0)['text']
            code_match = re.search(r'\b[RM]\d{3}\b', title)
            code = code_match[0] if code_match else 'result-' + re.search(r'\d+', title)[0]
            # Catalog numbering is presentation only; stable source IDs and links
            # remain bound to the archive and the editorial evidence.
            number = (int(code[1:]) if code.startswith('R') else
                      21 + int(code[1:]) if code.startswith('M') else
                      19 + int(code.removeprefix('result-')))
            # Card previews are source excerpts, never invented summaries.
            preview = next((b['text'] for b in blocks if b['type'] in ('p','li','h4')
                            and not re.match(r'^Респондент(?:ка)?(?: [RM]\d+)?[: ]+\[R\d+', b['text'])), '')
            if len(preview) > 180:
                preview = preview[:177].rsplit(' ', 1)[0] + '…'
            documents.append({'id':code, 'folder':group, 'title':f'Интервью {number}',
                              'catalog_number':number, 'source_title':title,
                              'filename':parts[-1], 'preview':preview, 'blocks':blocks})
            audit.append({'file':name, 'removed_blocks':removed,
                          'source_lines':len(lines), 'retained_lines':len(retained)})
    assert len({d['id'] for d in documents}) == len(documents)
    assert len({d['catalog_number'] for d in documents}) == len(documents)
    documents.sort(key=lambda d: (d['folder'], d['catalog_number']))
    return documents, audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, default=Path('public/customer-development.html'))
    parser.add_argument('--audit', type=Path)
    args = parser.parse_args()
    docs, audit = extract_archive(args.archive)
    editorial_path = Path(__file__).resolve().parents[1] / 'docs/customer-development-conclusions.json'
    editorial = json.loads(editorial_path.read_text())
    conclusion_audit = apply_conclusions(docs, editorial)
    payload = json.dumps({'folders':[{'id':i,'name':n} for i,n in GROUPS], 'documents':docs}, ensure_ascii=False, separators=(',', ':'))
    payload = payload.replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026')
    template = Path(__file__).with_name('customer-development-template.html').read_text()
    assert template.count('<!-- CUSTOMER_DEVELOPMENT_DATA -->') == 1
    args.output.write_text(template.replace('<!-- CUSTOMER_DEVELOPMENT_DATA -->', payload))
    if args.audit:
        args.audit.write_text(json.dumps({'extraction':audit, 'conclusions':conclusion_audit}, ensure_ascii=False, indent=2))
    print(json.dumps({'documents':len(docs), 'folders':{n:sum(d['folder']==i for d in docs) for i,n in GROUPS},
                      'removed_sections_and_action_fields':sum(len(a['removed_blocks']) for a in audit),
                      'rewritten_conclusions':len(conclusion_audit)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
