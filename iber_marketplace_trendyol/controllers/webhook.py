import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class TrendyolWebhookController(http.Controller):

    @http.route(
        '/trendyol/webhook/<int:config_id>/<string:token>',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def trendyol_webhook(self, config_id, token, **kwargs):
        """
        Trendyol webhook endpoint'i.
        Trendyol sipariş/durum değişikliklerini bu endpoint üzerinden alır.
        """
        # Ham veriyi oku
        try:
            raw_data = request.httprequest.get_data(as_text=True)
            payload = json.loads(raw_data) if raw_data else {}
        except Exception:
            payload = {}

        # Konfigürasyonu bul ve token doğrula
        try:
            config = request.env['iber.marketplace.trendyol.config'].sudo().browse(config_id)
            if not config.exists():
                _logger.warning(
                    'Trendyol webhook: config_id=%s bulunamadı.', config_id)
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'config not found'}),
                    headers=[('Content-Type', 'application/json')],
                    status=404,
                )

            if config.webhook_token and config.webhook_token != token:
                _logger.warning(
                    'Trendyol webhook: geçersiz token, config_id=%s.', config_id)
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'invalid token'}),
                    headers=[('Content-Type', 'application/json')],
                    status=401,
                )
        except Exception as exc:
            _logger.exception('Trendyol webhook doğrulama hatası: %s', exc)
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(exc)}),
                headers=[('Content-Type', 'application/json')],
                status=500,
            )

        # Olayı logla
        try:
            event_type = payload.get('type') or payload.get('event') or 'unknown'
            order_number = (
                payload.get('orderNumber')
                or payload.get('order_number')
                or ''
            )
            _logger.info(
                'Trendyol webhook alındı: config_id=%s, event=%s, order_number=%s, payload=%s',
                config_id, event_type, order_number,
                json.dumps(payload, ensure_ascii=False)[:500],
            )

            # ir.logging'e yaz
            request.env['ir.logging'].sudo().create({
                'name': 'trendyol.webhook',
                'type': 'server',
                'level': 'INFO',
                'dbname': request.env.cr.dbname,
                'message': (
                    f'Trendyol webhook | config_id={config_id} | '
                    f'event={event_type} | order={order_number} | '
                    f'payload={json.dumps(payload, ensure_ascii=False)[:1000]}'
                ),
                'path': '/trendyol/webhook',
                'func': 'trendyol_webhook',
                'line': '0',
            })

            # Sipariş olayı ise hızlı senkronizasyon tetikle
            if order_number and event_type.lower() in (
                'order', 'order_status_changed', 'ordercreated',
                'orderstatuschanged', 'created', 'shipped',
            ):
                try:
                    wizard = request.env['iber.marketplace.trendyol.sync.wizard'].sudo().create({
                        'config_id': config_id,
                        'sync_type': 'orders',
                        'order_days_back': 1,
                    })
                    wizard._sync_orders()
                except Exception as sync_exc:
                    _logger.warning(
                        'Trendyol webhook sipariş sync hatası: %s', sync_exc)

        except Exception as exc:
            _logger.exception('Trendyol webhook işleme hatası: %s', exc)

        return request.make_response(
            json.dumps({'status': 'ok'}),
            headers=[('Content-Type', 'application/json')],
        )
