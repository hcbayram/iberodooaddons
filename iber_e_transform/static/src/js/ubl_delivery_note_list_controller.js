/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useService } from "@web/core/utils/hooks";
import { onWillUnmount } from "@odoo/owl";

/**
 * Odoo RPC hatalarını kullanıcı dostu mesaja çevirir.
 * Odoo server hataları error.data.message içinde gelir.
 */
function parseOdooError(error) {
    if (!error) return "Unknown error.";
    if (error?.data?.message) return error.data.message;
    if (error?.message) return error.message;
    return String(error);
}

export class UBLDeliveryNoteListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this._activeDateFilter = "son_30_gun";

        this._onErpdenUblOlustur  = this.onErpdenUblOlustur.bind(this);
        this._onGibGonder         = this.onGibGonder.bind(this);
        this._onGibSifirla        = this.onGibSifirla.bind(this);
        this._onPdfOnizle         = this.onPdfOnizle.bind(this);
        this._onTarihFiltre       = this.onTarihFiltre.bind(this);
        this._onEntegratorGetir   = this.onEntegratorGetir.bind(this);

        this.env.bus.addEventListener("ubl_dn:erp_ubl_olustur",  this._onErpdenUblOlustur);
        this.env.bus.addEventListener("ubl_dn:gib_gonder",       this._onGibGonder);
        this.env.bus.addEventListener("ubl_dn:gib_sifirla",      this._onGibSifirla);
        this.env.bus.addEventListener("ubl_dn:pdf_onizle",       this._onPdfOnizle);
        this.env.bus.addEventListener("ubl_dn:tarih_filtre",     this._onTarihFiltre);
        this.env.bus.addEventListener("ubl_dn:entegrator_getir", this._onEntegratorGetir);

        onWillUnmount(() => {
            this.env.bus.removeEventListener("ubl_dn:erp_ubl_olustur",  this._onErpdenUblOlustur);
            this.env.bus.removeEventListener("ubl_dn:gib_gonder",       this._onGibGonder);
            this.env.bus.removeEventListener("ubl_dn:gib_sifirla",      this._onGibSifirla);
            this.env.bus.removeEventListener("ubl_dn:pdf_onizle",       this._onPdfOnizle);
            this.env.bus.removeEventListener("ubl_dn:tarih_filtre",     this._onTarihFiltre);
            this.env.bus.removeEventListener("ubl_dn:entegrator_getir", this._onEntegratorGetir);
        });
    }

    onTarihFiltre(ev) {
        this._activeDateFilter = ev.detail;
    }

    _dateRangeFromPreset(preset) {
        const today = new Date();
        const pad = (n) => String(n).padStart(2, "0");
        const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
        const todayStr = fmt(today);
        if (preset === "bugun") {
            return { startCreateDate: todayStr, endCreateDate: todayStr };
        }
        if (preset === "bu_hafta") {
            const mon = new Date(today);
            mon.setDate(today.getDate() - ((today.getDay() + 6) % 7));
            return { startCreateDate: fmt(mon), endCreateDate: todayStr };
        }
        if (preset === "bu_ay") {
            const first = new Date(today.getFullYear(), today.getMonth(), 1);
            return { startCreateDate: fmt(first), endCreateDate: todayStr };
        }
        if (preset === "son_30_gun") {
            const d = new Date(today);
            d.setDate(d.getDate() - 30);
            return { startCreateDate: fmt(d), endCreateDate: todayStr };
        }
        return {};   // tumu → filtre yok
    }

    async onEntegratorGetir() {
        let uiFilters = {};
        if (this._activeDateFilter) {
            uiFilters = this._dateRangeFromPreset(this._activeDateFilter);
        }
        this.notification.add("Fetching incoming despatch advices...", { type: "info" });
        try {
            const result = await this.orm.call(
                "l10n_tr.ubl.delivery.note",
                "action_fetch_incoming_from_integrator",
                [],
                { ui_filters: uiFilters }
            );
            if (result) await this.action.doAction(result);
            await this.model.root.load();
            this.model.notify();
        } catch (error) {
            this.notification.add(
                "Error fetching despatch advice from integrator:\n" + parseOdooError(error),
                { type: "danger", sticky: true }
            );
        }
    }

    getSelectedResIds() {
        if (!this.model.root.selection || !this.model.root.selection.length) return [];
        return this.model.root.selection.map((r) => r.resId);
    }

    /** ERP'den UBL oluştur — seçim gerektirmez */
    async onErpdenUblOlustur() {
        this.notification.add("Starting UBL creation from ERP...", { type: "info" });
        try {
            const result = await this.orm.call(
                "l10n_tr.ubl.delivery.note",
                "action_sync_from_erp",
                []
            );
            if (result) await this.action.doAction(result);
            await this.model.root.load();
            this.model.notify();
        } catch (error) {
            this.notification.add(
                "ERP sync error:\n" + parseOdooError(error),
                { type: "danger", sticky: true }
            );
        }
    }

    /** GIB'e gönder — seçili satırlar */
    async onGibGonder() {
        const ids = this.getSelectedResIds();
        if (!ids.length) {
            this.notification.add("Please select at least one despatch advice.", { type: "warning" });
            return;
        }
        let successCount = 0;
        const errors = [];
        for (const id of ids) {
            try {
                const result = await this.orm.call(
                    "l10n_tr.ubl.delivery.note",
                    "action_send_to_ubl_service",
                    [[id]]
                );
                if (result?.type === "ir.actions.client") {
                    const params = result.params || {};
                    if (params.type === "success") successCount++;
                    else errors.push(`#${id}: ${params.message || "Unknown error"}`);
                } else {
                    successCount++;
                }
            } catch (error) {
                errors.push(`#${id}: ${parseOdooError(error)}`);
            }
        }
        await this.model.root.load();
        this.model.notify();

        if (successCount) {
            this.notification.add(
                `${successCount} despatch advice(s) sent to GIB successfully.`,
                { type: "success" }
            );
        }
        if (errors.length) {
            this.notification.add(
                "Send error:\n" + errors.join("\n"),
                { type: "danger", sticky: true }
            );
        }
    }

    /** PDF önizleme — tek kayıt */
    async onPdfOnizle() {
        const ids = this.getSelectedResIds();
        if (!ids.length) {
            this.notification.add("Please select a despatch advice.", { type: "warning" });
            return;
        }
        if (ids.length > 1) {
            this.notification.add("Select a single despatch advice for PDF preview.", { type: "warning" });
            return;
        }
        try {
            const result = await this.orm.call(
                "l10n_tr.ubl.delivery.note",
                "action_preview_pdf",
                [[ids[0]]]
            );
            await this.action.doAction(result);
        } catch (error) {
            this.notification.add(
                "Could not generate PDF:\n" + parseOdooError(error),
                { type: "danger", sticky: true }
            );
        }
    }

    /** GIB durumunu sıfırla */
    async onGibSifirla() {
        const ids = this.getSelectedResIds();
        if (!ids.length) {
            this.notification.add("Please select at least one despatch advice.", { type: "warning" });
            return;
        }
        try {
            await this.orm.write("l10n_tr.ubl.delivery.note", ids, {
                gib_status: "draft",
                gib_log: false,
            });
            this.notification.add(
                `GIB status reset for ${ids.length} despatch advice(s).`,
                { type: "success" }
            );
            await this.model.root.load();
            this.model.notify();
        } catch (error) {
            this.notification.add(
                "Status reset error:\n" + parseOdooError(error),
                { type: "danger", sticky: true }
            );
        }
    }
}

registry.category("views").add("ubl_delivery_note_list", {
    ...listView,
    Controller: UBLDeliveryNoteListController,
});
