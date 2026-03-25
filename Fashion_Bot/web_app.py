from aiohttp import web


async def handle_ping(request):
    """Обработчик главной страницы для проверки работоспособности Nginx"""
    return web.Response(text="Бот запущен в режиме Production. Nginx работает отлично! 🚀")


async def start_web_server():
    """Инициализация и запуск aiohttp сервера"""
    app = web.Application()
    app.router.add_get('/', handle_ping)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("Веб-сервер запущен на http://0.0.0.0:8080")
