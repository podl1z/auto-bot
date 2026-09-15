from bot.filters import matches_trigger

PHRASES = ["старт", "start", "го гулять"]


def test_ловит_точное_слово():
    assert matches_trigger("старт", PHRASES)
    assert matches_trigger("start", PHRASES)


def test_не_зависит_от_регистра():
    assert matches_trigger("СТАРТ", PHRASES)
    assert matches_trigger("Start", PHRASES)


def test_ловит_слово_в_предложении_и_с_пунктуацией():
    assert matches_trigger("ну давай, старт!", PHRASES)
    assert matches_trigger("(старт)", PHRASES)


def test_не_ловит_часть_слова():
    """Главная защита от того, чтобы бот здоровался на каждое сообщение."""
    assert not matches_trigger("стартап", PHRASES)
    assert not matches_trigger("рестарт", PHRASES)
    assert not matches_trigger("перестартовать", PHRASES)
    assert not matches_trigger("restarted", PHRASES)


def test_ловит_фразу_из_нескольких_слов():
    assert matches_trigger("ну что, го гулять?", PHRASES)
    assert not matches_trigger("го гулятьный", PHRASES)


def test_пустые_входные_данные():
    assert not matches_trigger("", PHRASES)
    assert not matches_trigger("старт", [])
    assert not matches_trigger("старт", ["", "   "])
