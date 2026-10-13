"""Standalone interview publication checks; no application/database mutations."""
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('custdev_builder', ROOT / 'scripts/build_customer_development.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def line(text, size=11, top=0, page=0, bold=0):
    return {'text':text, 'size':size, 'top':top, 'bottom':top+size, 'page':page, 'bold':bold}


class PublicationTests(unittest.TestCase):
    def test_action_block_keeps_following_transcript(self):
        source = [line('Основные выводы',15), line('Наблюдение'),
                  line('Дальнейшие шаги',11.5), line('Отправить приглашение'),
                  line('Принятые решения',11.5), line('Назначить встречу'),
                  line('Расшифровка',15), line('Респондент: В следующий раз было иначе.')]
        kept, removed = builder.remove_actions(source)
        self.assertEqual([x['text'] for x in kept], ['Основные выводы','Наблюдение','Расшифровка','Респондент: В следующий раз было иначе.'])
        self.assertEqual(removed, ['Дальнейшие шаги','Принятые решения'])

    def test_nested_test_headings_do_not_end_action_block(self):
        source = [line('Предлагаемый первый продуктовый тест',11.5), line('Сценарий',11.5),
                  line('Сделать прототип'), line('Что спросить в следующих интервью',11.5),
                  line('О покупке',11.5), line('Вопрос'), line('Ограничения исследования',11.5), line('Не проверена оплата')]
        kept, _ = builder.remove_actions(source)
        self.assertEqual([x['text'] for x in kept], ['Ограничения исследования','Не проверена оплата'])

    def test_action_fields_preserve_hypothesis_and_basis(self):
        source = [line('Гипотеза 1',11.5), line('Гипотеза: Нужны вопросы'),
                  line('Основание: Так говорит респондент'), line('Как проверить: Сравнить'),
                  line('два варианта'), line('Критерий решения: Повторная покупка'),
                  line('Гипотеза 2',11.5), line('Основание: Другое наблюдение')]
        kept, _ = builder.remove_actions(source)
        self.assertEqual(len(kept),5)
        self.assertEqual(kept[-1]['text'],'Основание: Другое наблюдение')

    def test_wrapped_question_and_page_continuation(self):
        source = [line('1. Интервьюер Расскажите о последнем',top=100,bold=1),
                  line('выступлении и ставках.',top=115.8,bold=1),
                  line('Респондент M001 Это была защита',top=138.6),
                  line('моей работы.',top=60,page=1)]
        blocks = builder.blocks_from_lines(source)
        self.assertEqual([b['type'] for b in blocks],['p','p'])
        self.assertEqual(blocks[0]['text'],'1. Интервьюер Расскажите о последнем выступлении и ставках.')
        self.assertEqual(blocks[1]['text'],'Респондент M001 Это была защита моей работы.')

    def test_published_archive_inventory_and_removals(self):
        html = (ROOT/'public/customer-development.html').read_text()
        raw = re.search(r'<script type="application/json" id="research-data">(.*?)</script>', html, re.S)[1]
        data = json.loads(raw)
        docs = data['documents']
        self.assertEqual(len(docs),39)
        self.assertEqual({f['name'] for f in data['folders']},{'Идеальный клиент','Другие сегменты'})
        self.assertEqual(sum(d['folder']=='ideal' for d in docs),28)
        self.assertEqual(sum(d['folder']=='other' for d in docs),11)
        self.assertEqual({d['id'] for d in docs}, {f'R{i:03}' for i in range(1,20)} | {f'M{i:03}' for i in range(1,19)} | {'result-01','result-02'})
        for doc in docs:
            self.assertTrue(doc['blocks'])
            for block in doc['blocks']:
                if block['type'].startswith('h'):
                    self.assertNotIn(block['text'],builder.ACTION_STARTS)
                self.assertFalse(builder.INLINE_ACTION.match(block['text']))
            if doc['id'].startswith('M'):
                self.assertEqual(len(doc['links']),1)
                self.assertIn('Связанные материалы',[b['text'] for b in doc['blocks']])
        for id in ('R013','R017','R018'):
            self.assertIn('Расшифровка',[b['text'] for d in docs if d['id']==id for b in d['blocks']])
        self.assertNotIn('<',raw)
        self.assertNotIn('fetch(',html)
        self.assertNotIn('localStorage',html)


if __name__ == '__main__':
    unittest.main()
