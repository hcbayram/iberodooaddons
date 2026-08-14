/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useService } from "@web/core/utils/hooks";
import { onWillUnmount } from "@odoo/owl";

function parseOdooError(error) {
    if (!error) return "Bilinmeyen hata.";
    if (error?.data?.message) return error.data.message;
    if (error?.message) return error.message;
    return String(error);
}

export class UBLInvoiceListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this._onFaturaGuncelle          = this.onFaturaGuncelle.bind(this);
        this._onEntegratorGetir         = this.onEntegratorGetir.bind(this);
        this._onSonNGetir               = this.onSonNGetir.bind(this);
        this._onUuidIleGetir            = this.onUuidIleGetir.bind(this);
        this._onXmlIceAktar             = this.onXmlIceAktar.bind(this);
        this._onGibGonder               = this.onGibGonder.bind(this);
        this._onGibSifirla              = this.onGibSifirla.bind(this);
        this._onPdfOnizle               = this.onPdfOnizle.bind(this);
        this._onTarihFiltre             = this.onTarihFiltre.bind(this);
        this._onSistemFaturasıDonustur  = this.onSistemFaturasıDonustur.bind(this);

        // Aktif tarih filtresi (toolbar butonlarından seçilen)
        this._activeDateFilter   = "son_30_gun";

        this.env.bus.addEventListener("ubl_inv:fatura_guncelle",          this._onFaturaGuncelle);
        this.env.bus.addEventListener("ubl_inv:entegrator_getir",         this._onEntegratorGetir);
        this.env.bus.addEventListener("ubl_inv:son_n_getir",              this._onSonNGetir);
        this.env.bus.addEventListener("ubl_inv:uuid_ile_getir",           this._onUuidIleGetir);
        this.env.bus.addEventListener("ubl_inv:xml_ice_aktar",            this._onXmlIceAktar);
        this.env.bus.addEventListener("ubl_inv:gib_gonder",               this._onGibGonder);
        this.env.bus.addEventListener("ubl_inv:gib_sifirla",              this._onGibSifirla);
        this.env.bus.addEventListener("ubl_inv:pdf_onizle",               this._onPdfOnizle);
        this.env.bus.addEventListener("ubl_inv:tarih_filtre",             this._onTarihFiltre);
        this.env.bus.addEventListener("ubl_inv:sistem_faturasi_donustur", this._onSistemFaturasıDonustur);

        onWillUnmount(() => {
            this.env.bus.removeEventListener("ubl_inv:fatura_guncelle",          this._onFaturaGuncelle);
            this.env.bus.removeEventListener("ubl_inv:entegrator_getir",         this._onEntegratorGetir);
            this.env.bus.removeEventListener("ubl_inv:son_n_getir",              this._onSonNGetir);
            this.env.bus.removeEventListener("ubl_inv:uuid_ile_getir",           this._onUuidIleGetir);
            this.env.bus.removeEventListener("ubl_inv:xml_ice_aktar",            this._onXmlIceAktar);
            this.env.bus.removeEventListener("ubl_inv:gib_gonder",               this._onGibGonder);
            this.env.bus.removeEventListener("ubl_inv:gib_sifirla",              this._onGibSifirla);
            this.env.bus.removeEventListener("ubl_inv:pdf_onizle",               this._onPdfOnizle);
            this.env.bus.removeEventListener("ubl_inv:tarih_filtre",             this._onTarihFiltre);
            this.env.bus.removeEventListener("ubl_inv:sistem_faturasi_donustur", this._onSistemFaturasıDonustur);
        });
    }

    getSelectedResIds() {
        if (!this.model.root.selection || !this.model.root.selection.length) return [];
        return this.model.root.selection.map((r) => r.resId);
    }

    /** Giden faturalar — Odoo'dan senkronize et */
    async onFaturaGuncelle() {
        this.notification.add("Faturalar güncelleniyor...", { type: "info" });
        try {
            const result = await this.orm.call(
                "l10n_tr.ubl.invoice", "action_sync_outgoing_from_erp", []
            );
            if (result) await this.action.doAction(result);
            await this.model.root.load();
            this.model.notify();
        } catch (error) {
            this.notification.add(
                "Güncelleme hatası:\n" + parseOdooError(error),
                { type: "danger", sticky: true }
            );
        }
    }

    /** Gelen faturalar — Entegratörden getir */
    async onEntegratorGetir() {
        this.notification.add("Entegratörden faturalar alınıyor...", { type: "info" });
        try {
            // Önce toolbar preset'i, yoksa domain filtrelerini kullan
            let filters = {};
            if (this._activeDateFilter) {
                filters = this._dateRangeFromPreset(this._activeDateFilter);
            } else {
                filters = this._extractDateFilters();
            }
            const result = await this.orm.call(
                "l10n_tr.ubl.invoice", "action_fetch_incoming_from_integrator", [[], filters]
            );
            if (result) await this.action.doAction(result);
            await this.model.root.load();
            this.model.notify();
        } catch (error) {
            this.notification.add(
                "Fatura alma hatası:\n" + parseOdooError(error),
                { type: "danger", sticky: true }
            );
        }
    }

    /** Gelen faturalar — Test amaçlı: son N faturayı getir (tarih filtresiz) */
    async onSonNGetir() {
        this.notification.add("Entegratörden son 10 fatura alınıyor...", { type: "info" });
        try {
            const result = await this.orm.call(
                "l10n_tr.ubl.invoice", "action_fetch_last_n_incoming_from_integrator", [10]
            );
            if (result) await this.action.doAction(result);
            await this.model.root.load();
            this.model.notify();
        } catch (error) {
            this.notification.add(
                "Fatura alma hatası:\n" + parseOdooError(error),
                { type: "danger", sticky: true }
            );
        }
    }

    /** Gelen faturalar — bilinen bir UUID (GUID) ile entegratörden tekil belge çeker */
    async onUuidIleGetir() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "edn.invoice.uuid.fetch.wizard",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
        });
        await this.model.root.load();
        this.model.notify();
    }

    /** Gelen faturalar — ham UBL-TR XML'inden elle içe aktar */
    async onXmlIceAktar() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "edn.invoice.xml.import.wizard",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
        });
        await this.model.root.load();
        this.model.notify();
    }

    /** Toolbar tarih filtre butonu */
    onTarihFiltre(ev) {
        const preset = ev.detail || ev;
        this._activeDateFilter = preset === "tumu" ? null : preset;
        const label = { bugun: "Bugün", bu_hafta: "Bu Hafta", bu_ay: "Bu Ay",
                        son_30_gun: "Son 30 Gün", tumü: "Tümü" }[preset] || preset;
        this.notification.add(`Filtre: ${label}`, { type: "info" });
    }

    /** Seçili preset'ten tarih aralığı hesaplar */
    _dateRangeFromPreset(preset) {
        const today = new Date();
        const fmt = (d) => d.toISOString().slice(0, 10);
        let start, end;
        switch (preset) {
            case "bugun":
                start = end = fmt(today);
                break;
            case "bu_hafta":
                start = fmt(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6));
                end   = fmt(today);
                break;
            case "bu_ay":
                start = fmt(new Date(today.getFullYear(), today.getMonth(), 1));
                end   = fmt(new Date(today.getFullYear(), today.getMonth() + 1, 0));
                break;
            case "son_30_gun":
            default:
                start = fmt(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29));
                end   = fmt(today);
                break;
        }
        return { startCreateDate: start + "T00:00:00", endCreateDate: end + "T23:59:59" };
    }

    /** Aktif Odoo domain'inden tarih koşullarını okur */
    _extractDateFilters() {
        const filters = {};
        const domain = this.model?.root?.domain || [];
        for (const condition of domain) {
            if (!Array.isArray(condition) || condition.length !== 3) continue;
            const [field, operator, value] = condition;
            if (!value) continue;

            // issue_date → startDate / endDate (NES: fatura tarihi)
            if (field === "issue_date") {
                if (operator === ">=" || operator === ">") {
                    filters.startDate = value.slice(0, 10) + "T00:00:00";
                } else if (operator === "<=" || operator === "<") {
                    filters.endDate = value.slice(0, 10) + "T23:59:59";
                } else if (operator === "=") {
                    filters.startDate = value.slice(0, 10) + "T00:00:00";
                    filters.endDate   = value.slice(0, 10) + "T23:59:59";
                }
            }

            // gib_send_date → startCreateDate / endCreateDate (NES: geliş tarihi)
            if (field === "gib_send_date" || field === "erp_last_sync_date") {
                if (operator === ">=" || operator === ">") {
                    filters.startCreateDate = value.slice(0, 10) + "T00:00:00";
                } else if (operator === "<=" || operator === "<") {
                    filters.endCreateDate = value.slice(0, 10) + "T23:59:59";
                } else if (operator === "=") {
                    filters.startCreateDate = value.slice(0, 10) + "T00:00:00";
                    filters.endCreateDate   = value.slice(0, 10) + "T23:59:59";
                }
            }
        }
        return filters;
    }

    /** GIB'e gönder — seçili satırlar */
    async onGibGonder() {
        const ids = this.getSelectedResIds();
        if (!ids.length) {
            this.notification.add("Lütfen en az bir fatura seçin.", { type: "warning" });
            return;
        }
        let successCount = 0;
        const errors = [];
        for (const id of ids) {
            try {
                const result = await this.orm.call(
                    "l10n_tr.ubl.invoice", "action_send_to_ubl_service", [[id]]
                );
                if (result?.type === "ir.actions.client") {
                    const params = result.params || {};
                    if (params.type === "success") successCount++;
                    else errors.push(`#${id}: ${params.message || "Bilinmeyen hata"}`);
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
                `${successCount} fatura başarıyla GIB'e gönderildi.`,
                { type: "success" }
            );
        }
        if (errors.length) {
            this.notification.add(
                "Gönderim hatası:\n" + errors.join("\n"),
                { type: "danger", sticky: true }
            );
        }
    }

    /** PDF önizleme — tek kayıt */
    async onPdfOnizle() {
        const ids = this.getSelectedResIds();
        if (!ids.length) {
            this.notification.add("Lütfen bir fatura seçin.", { type: "warning" });
            return;
        }
        if (ids.length > 1) {
            this.notification.add("PDF önizleme için tek bir fatura seçin.", { type: "warning" });
            return;
        }
        try {
            const result = await this.orm.call(
                "l10n_tr.ubl.invoice", "action_preview_pdf", [[ids[0]]]
            );
            await this.action.doAction(result);
        } catch (error) {
            this.notification.add(
                "PDF oluşturulamadı:\n" + parseOdooError(error),
                { type: "danger", sticky: true }
            );
        }
    }

    /** Seçili gelen faturaları sistem faturasına dönüştür */
    async onSistemFaturasıDonustur() {
        const ids = this.getSelectedResIds();
        if (!ids.length) {
            this.notification.add("Lütfen en az bir fatura seçin.", { type: "warning" });
            return;
        }
        try {
            // Liste ekranında çoklu seçim mümkün olduğundan oluşan faturaya
            // yönlendirme yapmıyoruz; sadece oluşturup listeyi yeniliyoruz.
            const count = await this.orm.call(
                "l10n_tr.ubl.invoice", "action_convert_to_account_move_silent", [ids]
            );
            this.notification.add(
                `${count} fatura sistem faturasına dönüştürüldü.`,
                { type: "success" }
            );
            await this.model.root.load();
            this.model.notify();
        } catch (error) {
            this.notification.add(
                "Dönüştürme hatası:\n" + parseOdooError(error),
                { type: "danger", sticky: true }
            );
        }
    }

    /** GIB durumunu sıfırla */
    async onGibSifirla() {
        const ids = this.getSelectedResIds();
        if (!ids.length) {
            this.notification.add("Lütfen en az bir fatura seçin.", { type: "warning" });
            return;
        }
        try {
            await this.orm.write("l10n_tr.ubl.invoice", ids, {
                gib_status: "draft",
                gib_log: false,
            });
            this.notification.add(
                `${ids.length} faturanın GIB durumu sıfırlandı.`,
                { type: "success" }
            );
            await this.model.root.load();
            this.model.notify();
        } catch (error) {
            this.notification.add(
                "Durum sıfırlama hatası:\n" + parseOdooError(error),
                { type: "danger", sticky: true }
            );
        }
    }
}

registry.category("views").add("ubl_invoice_list", {
    ...listView,
    Controller: UBLInvoiceListController,
});
