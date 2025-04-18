import unittest
from scraper import split_into_sentences, save_chunk

class TestSplitIntoSentences(unittest.TestCase):
    def test_basic_sentence_splitting(self):
        text = "This is a sentence. This is another sentence! And here's a third one?"
        expected = [
            "This is a sentence.",
            "This is another sentence!",
            "And here's a third one?"
        ]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_empty_text(self):
        text = ""
        expected = []
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_single_sentence(self):
        text = "This is a single sentence."
        expected = ["This is a single sentence."]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_parentheses_handling(self):
        text = "This is a sentence (with parentheses inside). This is another sentence."
        expected = [
            "This is a sentence (with parentheses inside).",
            "This is another sentence."
        ]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_sentence_in_parentheses_handling(self):
        text = "This is a sentence (And this is another sentence inside. And another one.). This is another sentence."
        expected = [
            "This is a sentence (And this is another sentence inside. And another one.).",
            "This is another sentence."
        ]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_nested_parentheses(self):
        text = "First sentence (with (nested) parentheses). Second sentence."
        expected = [
            "First sentence (with (nested) parentheses).",
            "Second sentence."
        ]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_nested_parentheses_contain_sentences(self):
        text = "First sentence (The sentence has parentheses (And this is a sentence inside the nested parentheses. And another one.). And this is second sentence.). Second sentence outside (and some comments). (And this is third sentence.)"
        expected = [
            "First sentence (The sentence has parentheses (And this is a sentence inside the nested parentheses. And another one.). And this is second sentence.).",
            "Second sentence outside (and some comments).",
            "(And this is third sentence.)"
        ]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_multiple_spaces(self):
        text = "First    sentence.    Second    sentence."
        expected = [
            "First    sentence.",
            "Second    sentence."
        ]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_no_ending_punctuation(self):
        text = "This is a sentence without ending punctuation"
        expected = ["This is a sentence without ending punctuation"]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_unmatched_closing_parentheses(self):
        text = "This is a sentence). This is another sentence. This is a third sentence."
        expected = [
            "This is a sentence).",
            "This is another sentence.",
            "This is a third sentence."
        ]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_mixed_parentheses(self):
        text = "First sentence (with opening paren. Second sentence.). Third sentence). Fourth sentence."
        expected = [
            "First sentence (with opening paren. Second sentence.).",
            "Third sentence).",
            "Fourth sentence."
        ]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_numbered_items(self):
        text = "1. First item. 2. Second item. 3. Third item with multiple sentences. This is another sentence. 4. Fourth item."
        expected = [
            "1. First item.",
            "2. Second item.",
            "3. Third item with multiple sentences.",
            "This is another sentence.",
            "4. Fourth item."
        ]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

    def test_mixed_numbered_items(self):
        text = "Regular sentence. 1. Numbered item. Another regular sentence. 2. Another numbered item with (parentheses). 3. Final numbered item."
        expected = [
            "Regular sentence.",
            "1. Numbered item.",
            "Another regular sentence.",
            "2. Another numbered item with (parentheses).",
            "3. Final numbered item."
        ]
        result = split_into_sentences(text)
        self.assertEqual(result, expected)

class TestSaveChunk(unittest.TestCase):
    def setUp(self):
        self.current_chapter = {
            'number': '1',
            'title': 'Test Chapter'
        }
        self.current_article = {
            'number': '1',
            'title': 'Test Article'
        }
        self.chunks = []

    def test_empty_content(self):
        result = save_chunk([], self.current_chapter, self.current_article, self.chunks)
        self.assertEqual(result, [])

    def test_single_chunk_under_limit(self):
        content = "This is a test content that is under the limit."
        result = save_chunk(content, self.current_chapter, self.current_article, self.chunks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['content'], "This is a test content that is under the limit.")
        self.assertEqual(result[0]['chapter'], self.current_chapter)
        self.assertEqual(result[0]['article'], self.current_article)

    def test_multiple_chunks_over_limit(self):
        # Create content that will exceed the max_content_length
        long_content = " ".join(f"Sentence {i+1}: This is a very long sentence." for i in range(100))  # This should create a long string
        result = save_chunk(long_content, self.current_chapter, self.current_article, self.chunks, max_content_length=100)
        self.assertGreater(len(result), 1)
        # Verify each chunk is under the limit
        for chunk in result:
            self.assertLessEqual(len(chunk['content']), 100)
            self.assertEqual(chunk['chapter'], self.current_chapter)
            self.assertEqual(chunk['article'], self.current_article)

    def test_multiple_content_parts(self):
        content = "First part of the content. Second part of the content. Third part of the content."
        result = save_chunk(content, self.current_chapter, self.current_article, self.chunks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['content'], content)

    def test_none_chapter_and_article(self):
        content = "Test content"
        result = save_chunk(content, None, None, self.chunks)
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]['chapter'])
        self.assertIsNone(result[0]['article'])

    def test_custom_max_content_length(self):
        content = " ".join("This is a test sentence." for _ in range(5))  # Create content that's just over 50 chars
        result = save_chunk(content, self.current_chapter, self.current_article, self.chunks, max_content_length=50)
        self.assertGreater(len(result), 1)
        for chunk in result:
            self.assertLessEqual(len(chunk['content']), 50)

    def test_real_world_article(self):
        content = """1. Со дня вступления в силу настоящего Федерального закона признать утратившими силу:
1) Федеральный закон от 18 июля 1995 года N 108-ФЗ "О рекламе" (Собрание законодательства Российской Федерации, 1995, N 30, ст. 2864);
2) пункт 3 статьи 1 Федерального закона от 18 июня 2001 года N 76-ФЗ "О внесении изменений в некоторые законодательные акты Российской Федерации" (Собрание законодательства Российской Федерации, 2001, N 26, ст. 2580);
3) Федеральный закон от 14 декабря 2001 года N 162-ФЗ "О внесении изменений в статью 11 Федерального закона "О рекламе" (Собрание законодательства Российской Федерации, 2001, N 51, ст. 4827);
4) абзацы 23 и 24 статьи 3 Федерального закона от 30 декабря 2001 года N 196-ФЗ "О введении в действие Кодекса Российской Федерации об административных правонарушениях" (Собрание законодательства Российской Федерации, 2002, N 1, ст. 2);
5) Федеральный закон от 20 августа 2004 года N 115-ФЗ "О внесении изменения в статью 16 Федерального закона "О рекламе" (Собрание законодательства Российской Федерации, 2004, N 34, ст. 3530);
6) статью 55 Федерального закона от 22 августа 2004 года N 122-ФЗ "О внесении изменений в законодательные акты Российской Федерации и признании утратившими силу некоторых законодательных актов Российской Федерации в связи с принятием федеральных законов "О внесении изменений и дополнений в Федеральный закон "Об общих принципах организации законодательных (представительных) и исполнительных органов государственной власти субъектов Российской Федерации" и "Об общих принципах организации местного самоуправления в Российской Федерации" (Собрание законодательства Российской Федерации, 2004, N 35, ст. 3607);
7) статью 11 Федерального закона от 2 ноября 2004 года N 127-ФЗ "О внесении изменений в части первую и вторую Налогового кодекса Российской Федерации и некоторые другие законодательные акты Российской Федерации, а также о признании утратившими силу отдельных законодательных актов (положений законодательных актов) Российской Федерации" (Собрание законодательства Российской Федерации, 2004, N 45, ст. 4377);
8) статью 1 Федерального закона от 21 июля 2005 года N 113-ФЗ "О внесении изменений в Федеральный закон "О рекламе" и статью 14.3 Кодекса Российской Федерации об административных правонарушениях" (Собрание законодательства Российской Федерации, 2005, N 30, ст. 3124).
2. Впредь до приведения законов и иных нормативных правовых актов Российской Федерации, действующих на территории Российской Федерации и регулирующих отношения в сфере рекламы, в соответствие с настоящим Федеральным законом указанные законы и иные нормативные правовые акты применяются постольку, поскольку они не противоречат настоящему Федеральному закону.
3. Особенности размещения (распространения) рекламы в период проведения XXII Олимпийских зимних игр и XI Паралимпийских зимних игр 2014 года в городе Сочи определяются Федеральным законом "Об организации и о проведении XXII Олимпийских зимних игр и XI Паралимпийских зимних игр 2014 года в городе Сочи, развитии города Сочи как горноклиматического курорта и внесении изменений в отдельные законодательные акты Российской Федерации". (в ред. Федерального закона от 01.12.2007 N 310-ФЗ)
4. Особенности размещения (распространения) рекламы на территории инновационного центра "Сколково" устанавливаются Федеральным законом "Об инновационном центре "Сколково". (в ред. Федерального закона от 28.09.2010 N 243-ФЗ)
4.1. Особенности размещения (распространения) рекламы на территориях инновационных научно-технологических центров устанавливаются Федеральным законом "Об инновационных научно-технологических центрах и о внесении изменений в отдельные законодательные акты Российской Федерации". (в ред. Федерального закона от 29.07.2017 N 216-ФЗ)
5. Особенности размещения и распространения рекламы на территории Владивостокского городского округа в период организации проведения встречи глав государств и правительств стран - участников форума "Азиатско-тихоокеанское экономическое сотрудничество" в 2012 году в городе Владивостоке определяются Федеральным законом от 8 мая 2009 года N 93-ФЗ "Об организации проведения встречи глав государств и правительств стран - участников форума "Азиатско-тихоокеанское экономическое сотрудничество" в 2012 году, о развитии города Владивостока как центра международного сотрудничества в Азиатско-Тихоокеанском регионе и о внесении изменений в отдельные законодательные акты Российской Федерации". (в ред. Федерального закона от 05.04.2011 N 56-ФЗ)
6. Особенности размещения, распространения рекламы в период подготовки и проведения в Российской Федерации чемпионата мира по футболу FIFA 2018 года и Кубка конфедераций FIFA 2017 года устанавливаются Федеральным законом "О подготовке и проведении в Российской Федерации чемпионата мира по футболу FIFA 2018 года, Кубка конфедераций FIFA 2017 года, чемпионата Европы по футболу UEFA 2020 года и внесении изменений в отдельные законодательные акты Российской Федерации". (в ред. Федерального закона от 01.05.2019 N 100-ФЗ)
7. Полномочия органов местного самоуправления и органов государственной власти субъекта Российской Федерации в сфере рекламы, установленные настоящим Федеральным законом, могут быть перераспределены между ними в порядке, предусмотренном частью 1.2 статьи 17 Федерального закона от 6 октября 2003 года N 131-ФЗ "Об общих принципах организации местного самоуправления в Российской Федерации". (в ред. Федерального закона от 29.12.2014 N 485-ФЗ)
8. Особенности исполнения и заключения в 2022, 2023 и 2024 годах договоров на установку и эксплуатацию рекламных конструкций на земельном участке, здании или ином недвижимом имуществе, находящихся в государственной или муниципальной собственности, и на земельном участке, государственная собственность на который не разграничена, устанавливаются Федеральным законом от 8 марта 2022 года N 46-ФЗ "О внесении изменений в отдельные законодательные акты Российской Федерации". (в ред. Федеральных законов от 14.07.2022 N 286-ФЗ, от 23.04.2024 N 98-ФЗ)
9. Выдача разрешений на установку рекламных конструкций, аннулирование таких разрешений, выдача предписаний о демонтаже самовольно установленных рекламных конструкций на территории Военного инновационного технополиса "Эра" Министерства обороны Российской Федерации осуществляются федеральным органом исполнительной власти, осуществляющим функции по выработке и реализации государственной политики, нормативно-правовому регулированию в области обороны, с учетом положений Федерального закона "О Военном инновационном технополисе "Эра" Министерства обороны Российской Федерации и о внесении изменений в отдельные законодательные акты Российской Федерации". (в ред. Федерального закона от 14.07.2022 N 253-ФЗ)
10. Особенности размещения и распространения рекламы в период проведения в Российской Федерации международных соревнований "Всемирные игры дружбы" устанавливаются Федеральным законом "О международных соревнованиях "Всемирные игры дружбы" и о внесении изменений в отдельные законодательные акты Российской Федерации". (в ред. Федерального закона от 19.04.2024 N 80-ФЗ)"""

        result = save_chunk(content, self.current_chapter, self.current_article, self.chunks, max_content_length=1000)
        
        # Verify the content was split into multiple chunks due to length
        self.assertGreater(len(result), 1)
        
        # Verify each chunk has the correct structure
        for chunk in result:
            self.assertIn('chapter', chunk)
            self.assertIn('article', chunk)
            self.assertIn('content', chunk)
            self.assertLessEqual(len(chunk['content']), 2346)
            
        # Verify the content is preserved (check for key phrases)
        all_content = ' '.join(chunk['content'] for chunk in result)
        self.assertIn('1. Со дня вступления в силу настоящего Федерального закона', all_content)
        self.assertIn('Со дня вступления в силу настоящего Федерального закона', all_content)
        self.assertIn('Всемирные игры дружбы', all_content)

if __name__ == '__main__':
    unittest.main() 