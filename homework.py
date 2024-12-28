import logging
import os
import sys
import requests
import time

from telebot import TeleBot
from dotenv import load_dotenv


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(formatter)

logger.addHandler(stream_handler)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    env_vars = (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    for env_var in env_vars:
        if not env_var:
            logging.critical(
                f'Переменная окружения {env_var} недоступна.')
            return False
    return True


def send_message(bot, message):
    """Отправляет пользователю сообщение.

    Сообщает об изменившемся статусе домашней работы
     или о возникшей ошибке через Телеграмм-бот.
    """
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Сообщение отправлено: {message}')
    except Exception as error:
        logger.error(f'Ошибка при отправке сообщения: {error}')


def get_api_answer(timestamp):
    """Запрашивает данные через API Практикума."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != 200:
            error_message = (
                'Эндпоинт вернул ошибку: '
                f'{response.status_code}, {response.text}'
            )
            logger.error(error_message)
            raise requests.HTTPError(error_message)
        return response.json()
    except requests.RequestException as error:
        logger.error(f'Ошибка при запросе к API: {error}')
        raise RuntimeError('Ошибка при запросе к API Практикума') from error


def check_response(response):
    """Проверяет ответ сервера."""
    if not isinstance(response, dict):
        logger.error('Ответ API не является словарем.')
        raise TypeError('Ответ API не является словарем.')

    for key in ["homeworks", "current_date"]:
        if key not in response:
            logging.error(f'Ответ сервера не содержит ключа {key}.')
            raise KeyError(f'Ответ сервера не содержит ключа {key}.')

    if not isinstance(response['homeworks'], list):
        logger.error('Ключ "homeworks" не содержит список.')
        raise ('Ключ "homeworks" не содержит список.')

    return True


def parse_status(homework):
    """Извлекает из ответа статус домашней работы."""
    if "homework_name" not in homework:
        raise KeyError('Ключ "homework_name" отсутствует в ответе.')
    if "status" not in homework:
        raise KeyError('Ключ "status" отсутствует в ответе.')

    homework_name = homework["homework_name"]
    status = homework["status"]
    if status not in HOMEWORK_VERDICTS:
        logger.error(f'Неизвестный статус: {status}')
        raise ValueError(f'Неизвестный статус: {status}')
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(1)

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            api_response = get_api_answer(timestamp)
            check_response(api_response)
            homeworks = api_response.get("homeworks", [])
            if homeworks:
                message = parse_status(homeworks[-1])
                send_message(bot, message)
            else:
                logger.debug('Нет новых статусов домашних работ.')
            timestamp = api_response.get("current_date", timestamp)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
