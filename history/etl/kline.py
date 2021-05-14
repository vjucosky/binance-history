import aiofiles


from tortoise.transactions import atomic
from history.models import Symbol, KLine
from tortoise.queryset import QuerySet
from history.etl.base import BaseEtl
from zipfile import ZipFile
from pathlib import Path
from aiofiles import os


class KLineEtl(BaseEtl):
    @atomic()
    async def _load_file(self, file: Path, symbol: Symbol):
        klines = []

        async with aiofiles.open(file, 'r', encoding='UTF-8') as file:
            content = await file.read()

        for row in content.splitlines():
            data = row.split(',')

            if bool(data[11]):
                klines.append(
                    KLine(
                        symbol=symbol,
                        trade_count=data[8],
                        open_value=data[1],
                        high_value=data[2],
                        low_value=data[3],
                        close_value=data[4],
                        base_asset_volume=data[5],
                        base_asset_taker_buy_volume=data[9],
                        quote_asset_volume=data[7],
                        quote_asset_taker_buy_volume=data[10],
                        open_timestamp=data[0],
                        close_timestamp=data[6]
                    )
                )

        await KLine.bulk_create(klines, 10000)

    async def run(self, symbols: QuerySet):
        async for symbol in symbols.all():
            last_kline = await KLine.filter(symbol=symbol).order_by('-open_timestamp').first()

            if last_kline:
                last_period = self.get_date_object(last_kline.open_timestamp)
                periods = self.generate_periods(last_period)
            else:
                periods = self.generate_periods()

            for period in periods:
                file = f'{symbol.name}-1m-{period.year}-{period.month:02d}'

                if await self.download_file(f'https://data.binance.vision/data/spot/monthly/klines/{symbol.name}/1m/{file}.zip'):
                    with ZipFile(f'./stage/{file}.zip', 'r') as zipfile:
                        zipfile.extract(f'{file}.csv', './stage')

                    await self._load_file(f'./stage/{file}.csv', symbol)

                    await os.remove(f'./stage/{file}.zip')
                    await os.remove(f'./stage/{file}.csv')

        self.logger.info('Sincronização dos dados dos gráficos candlestick concluída')
