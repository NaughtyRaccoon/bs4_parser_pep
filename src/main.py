import re
import logging
from urllib.parse import urljoin
from collections import defaultdict

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from constants import BASE_DIR, MAIN_DOC_URL, MAIN_PEP_URL, EXPECTED_STATUS
from configs import configure_argument_parser, configure_logging
from outputs import control_output
from utils import get_response, find_tag, get_soup
from exceptions import VersionsNotFound


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')

    soup = get_soup(session, whats_new_url)
    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all(
        'li', attrs={'class': 'toctree-l1'}
    )

    results = [('Ссылка на статью', 'Заголовок', 'Редактор, автор')]
    for section in tqdm(sections_by_python):
        version_a_tag = section.find('a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)

        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, features='lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append(
            (version_link, h1.text, dl_text)
        )

    return results


def latest_versions(session):
    soup = get_soup(session, MAIN_DOC_URL)

    sidebar = find_tag(soup, 'div', attrs={'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')

    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise VersionsNotFound('Ничего не нашлось')

    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ''
        results.append(
            (link, version, status)
        )

    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')

    soup = get_soup(session, downloads_url)

    main_tag = find_tag(soup, 'div', attrs={'role': 'main'})
    table_tag = find_tag(main_tag, 'table', attrs={'class': 'docutils'})
    pdf_a4_tag = find_tag(
        table_tag, 'a', attrs={'href': re.compile(r'.+pdf-a4\.zip$')}
    )

    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)

    filename = archive_url.split('/')[-1]
    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename

    response = session.get(archive_url)

    with open(archive_path, 'wb') as file:
        file.write(response.content)

    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    numerical_index_url = urljoin(MAIN_PEP_URL, 'numerical/')
    response = get_response(session, numerical_index_url)
    soup = BeautifulSoup(response.text, features='lxml')
    tbody = find_tag(soup, 'tbody')
    pep_list = tbody.find_all('tr')
    status_counter = defaultdict(int)
    total_pep = 0
    mismatched_statuses = []
    result = [('Статус', 'Количество')]

    for row in tqdm(pep_list):
        href = row.a['href']
        preview_status = row.abbr.text[1:]
        pep_link = urljoin(MAIN_PEP_URL, href)

        response = get_response(session, pep_link)
        soup = BeautifulSoup(response.text, features='lxml')
        dl = find_tag(soup, 'dl')
        for tag in dl:
            if 'Status:' in tag.text:
                card_status = tag.next_sibling.next_sibling.string
                expected = EXPECTED_STATUS.get(preview_status)
                if expected is None or card_status not in expected:
                    mismatched_statuses.append({
                        'url': pep_link,
                        'card_status': card_status,
                        'expected_statuses': expected or []
                    })
                status_counter[card_status] += 1
                total_pep += 1
    # Формируем итоговую таблицу
    result.extend(sorted(status_counter.items()))
    result.append(('Total', total_pep))

    if mismatched_statuses:
        for mismatch in mismatched_statuses:
            logging.info('Несовпадающие статусы:')
            logging.info(f"URL: {mismatch['url']}")
            logging.info(f"Статус в карточке: {mismatch['card_status']}")
            logging.info(
                f"Ожидаемые статусы: "
                f"{', '.join(mismatch['expected_statuses'])}"
            )
            logging.info("-" * 50)

    return result


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')

    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')

    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()

    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)

    if results is not None:
        control_output(results, args)

    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
