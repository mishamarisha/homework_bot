import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import json
from dotenv import load_dotenv
from telebot import TeleBot, apihelper


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

formatter = logging.Formatter(
    '%(asctime)s - %(funcName)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(formatter)

logger.addHandler(stream_handler)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    env_vars = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    missing_vars = [name for name, value in env_vars.items() if not value]
    if missing_vars:
        for var in missing_vars:
            logging.critical(f'Переменная окружения "{var}" недоступна.')
        return False
    return True


def send_message(bot, message):
    """Отправляет пользователю сообщение.

    Сообщает об изменившемся статусе домашней работы
     или о возникшей ошибке через Телеграмм-бот.
    """
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except apihelper.ApiException as error:
        if "Bad Request" in str(error):
            logger.error(f'Некорректные параметры запроса: {error}')
        else:
            logger.error(f'Ошибка при обращении к Telegram API: {error}')
    except apihelper.ApiException as error:
        logger.error(f'Ошибка при отправке сообщения в Telegram API: {error}')
    else:
        logger.debug(f'Сообщение отправлено: {message}')


def get_api_answer(timestamp):
    """Запрашивает данные через API Практикума."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != HTTPStatus.OK:
            error_message = (
                'Эндпоинт вернул ошибку: '
                f'{response.status_code}, {response.text}'
            )
            logger.error(error_message)
            raise requests.HTTPError(error_message)
    except requests.RequestException as error:
        message = f'Ошибка при запросе к API: {error}'
        logger.error(message)
        raise RuntimeError(message) from error
    try:
        return response.json()
    except json.JSONDecodeError as error:
        logger.error(
            f'Ошибка декодирования JSON: {error}. '
            f'Ответ от сервера: {response.text}'
        )
        raise ValueError('Ошибка при декодировании JSON-ответа') from error
    except requests.RequestException as error:
        logger.error(f'Ошибка при запросе к API: {error}')
        raise RuntimeError('Ошибка при запросе к API Практикума') from error


def check_response(response):
    """Проверяет ответ сервера."""
    if not isinstance(response, dict):
        logger.error('Ответ API не является словарем.')
        raise TypeError('Ответ API не является словарем.')

    if 'homeworks' not in response:
        logger.error('Ответ сервера не содержит ключа "homeworks".')
        raise KeyError('Ответ сервера не содержит ключа "homeworks".')

    if 'current_date' not in response:
        logger.warning('Ответ сервера не содержит ключа "current_date".')
    else:
        if not isinstance(response['current_date'], (int)):
            message = (
                f'Значение ключа "current_date" должно быть числом, '
                f'получено {type(response["current_date"]).__name__}.'
            )
            logger.error(message)
            raise TypeError(message)

    if not isinstance(response['homeworks'], list):
        logger.error('Ключ "homeworks" не содержит список.')
        raise ('Ключ "homeworks" не содержит список.')


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


def send_error_message(error, last_message, bot):
    """Отправляет сообщение об ошибке, если оно отличается от последнего."""
    message = f'Сбой в работе программы: {error}'
    logger.error(message)
    if message != last_message:
        send_message(bot, message)
        return message
    return last_message


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(1)

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = None

    while True:
        try:
            api_response = get_api_answer(timestamp)
            check_response(api_response)
            homeworks = api_response.get("homeworks", [])
            if homeworks:
                message = parse_status(homeworks[-1])
                if message != last_message:
                    send_message(bot, message)
                    last_message = message
                else:
                    logger.debug('Нет новых статусов домашних работ.')
            else:
                logger.debug('Нет новых статусов домашних работ.')
            current_date = api_response.get("current_date", timestamp)
            timestamp = current_date if current_date else int(time.time())

        except (requests.RequestException, ValueError, Exception) as error:
            last_message = send_error_message(error, last_message, bot)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
