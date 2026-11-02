from app.engines.basketball import BasketballEngine
from app.engines.football import FootballEngine
from app.engines.tennis import TennisEngine
from app.models import Sport

ENGINES = {Sport.football: FootballEngine, Sport.basketball: BasketballEngine, Sport.tennis: TennisEngine}


def make_engine(sport: Sport):
    return ENGINES[sport]()
