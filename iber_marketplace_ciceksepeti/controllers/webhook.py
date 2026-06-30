import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CiceksepetiWebhookController(http.Controller):

    @http.route(
        '/ciceksepeti/webhook/<int:config_id>/<string:token>',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def ciceksepeti_webhook(self, config_id, token, **kwargs):
        """
        Çiçeksepeti webhook endpoint'i.
        Çiçeksepeti sipariş/durum değişikliklerini bu endpoint üzerinden alır.
        """
        # Ham veriyi oku
        try:
            raw_data = request.httprequest.get_data(as_text=True)
            payload = json.loads(raw_data) if raw_data else {}
        except Exception:
            payload = {}

        # Konfigürasyonu bul ve token doğrula
        try:
            config = request.env['iber.marketplace.ciceksepeti.config'].sudo().browse(config_id)
            if not config.exists():
                _logger.warning(
                    'Çiçeksepeti webhook: config_id=%s bulunamadı.', config_id)
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'config not found'}),
                    headers=[('Content-Type', 'application/json')],
                    status=404,
                )

            if config.webhook_token and config.webhook_token != token:
                _logger.warning(
                    'Çiçeksepeti webhook: geçersiz token, config_id=%s.', config_id)
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'invalid token'}),
                    headers=[('Content-Type', 'application/json')],
                    status=401,
                )
        except Exception as exc:
            _logger.exception('Çiçeksepeti webhook doğrulama hatası: %s', exc)
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(exc)}),
                headers=[('Content-Type', 'application/json')],
                status=500,
            )

        # Olayı logla
        try:
            order_code = (
                payload.get('orderCode')
                or payload.get('order_code')
                or ''
            )
            event_type = payload.get('type') or payload.get('event') or 'unknown'
            _logger.info(
                'Çiçeksepeti webhook alındı: config_id=%s, event=%s, orderCode=%s, payload=%s',
                config_id, event_type, order_code,
                json.dumps(payload, ensure_ascii=False)[:500],
            )

            # ir.logging'e yaz
            request.env['ir.logging'].sudo().create({
                'name': 'ciceksepeti.webhook',
                'type': 'server',
                'level': 'INFO',
                'dbname': request.env.cr.dbname,
                'message': (
                    f'Çiçeksepeti webhook | config_id={config_id} | '
                    f'event={event_type} | orderCode={order_code} | '
                    f'payload={json.dumps(payload, ensure_ascii=False)[:1000]}'
                ),
                'path': '/ciceksepeti/webhook',
                'func': 'ciceksepeti_webhook',
                'line': '0',
            })

            # Sipariş olayı ise hızlı senkronizasyon tetikle
            if order_code:
                try:
                    wizard = request.env[
                        'iber.marketplace.ciceksepeti.sync.wizard'
                    ].sudo().create({
                        'config_id': config_id,
                        'sync_type': 'orders',
                        'order_days_back': 1,
                    })
                    wizard._sync_orders()
                except Exception as sync_exc:
                    _logger.warning(
                        'Çiçeksepeti webhook sipariş sync hatası: %s', sync_exc)

        except Exception as exc:
            _logger.exception('Çiçeksepeti webhook işleme hatası: %s', exc)

        return request.make_response(
            json.dumps({'status': 'ok'}),
            headers=[('Content-Type', 'application/json')],
        )
