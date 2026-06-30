from lxml import etree
from io import BytesIO
from tempfile import NamedTemporaryFile
from odoo import _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_round, file_open
import logging
logger = logging.getLogger(__name__)

class UBLGenerator(object):
    def __init__(self):
        self.version='2.1'
        self.customization='TR1.2'
        self.doc_name = 'Invoice-2'

    def _generate_invoice_ubl_xml_etree(self,invoice_to_convert):       
        self.document = invoice_to_convert
        
        self.nsmap, self.ns = self._ubl_get_nsmap_namespace()
        self.document.UBLVersionID.value = self.version
        self.document.CustomizationID.value = self.customization
        attr_qname = etree.QName("http://www.w3.org/2001/XMLSchema-instance", "schemaLocation")
        xml_root = etree.Element('Invoice',{attr_qname: 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2 UBL-Invoice-2.1.xsd'}, nsmap=self.nsmap)
        self._create_ubl(xml_root)
        xml_string = etree.tostring(
            xml_root, pretty_print=True, encoding='UTF-8',
            xml_declaration=True)
        self._ubl_check_xml_schema(xml_string, 'Invoice', version=self.version)
        logger.debug(
            'Invoice UBL XML file generated for account invoice ID %s '
            '(state %s)', self.document.UUID.value, "OK")
        #logger.debug(xml_string.decode('utf-8'))
        return xml_string,self.document.UUID.value
    
    def _generate_despatch_ubl_xml_etree(self,despatch_to_convert):
        self.document = despatch_to_convert
        self.doc_name = 'DespatchAdvice-2'

        self.nsmap, self.ns = self._ubl_get_nsmap_namespace()
        self.document.UBLVersionID.value = self.version
        self.document.CustomizationID.value = self.customization
        attr_qname = etree.QName("http://www.w3.org/2001/XMLSchema-instance", "schemaLocation")
        xml_root = etree.Element('DespatchAdvice',{attr_qname: 'urn:oasis:names:specification:ubl:schema:xsd:DespatchAdvice-2 UBL-DespatchAdvice-2.1.xsd'}, nsmap=self.nsmap)
        self._create_ubl(xml_root)
        xml_string = etree.tostring(
            xml_root, pretty_print=True, encoding='UTF-8',
            xml_declaration=True)
        self._ubl_check_xml_schema(xml_string, 'DespatchAdvice', version=self.version)
        logger.debug(
            'DespatchAdvice UBL XML file generated for account Despatch ID %s '
            '(state %s)', self.document.UUID.value, "OK")
        #logger.debug(xml_string.decode('utf-8'))
        return xml_string,self.document.UUID.value
    
    def _ubl_check_xml_schema(self, xml_string, document, version='2.1'):
        """Validate the XML file against the XSD"""
        xsd_file = 'iber_service_layer/data/xsd-%s/maindoc/UBL-%s-%s.xsd' % (
            version, document, version)
        xsd_etree_obj = etree.parse(file_open(xsd_file))
        official_schema = etree.XMLSchema(xsd_etree_obj)
        try:
            t = etree.parse(BytesIO(xml_string))
            official_schema.assertValid(t)
        except Exception as e:
            # if the validation of the XSD fails, we arrive here
            logger = logging.getLogger(__name__)
            logger.warning(
                "The XML file is invalid against the XML Schema Definition")
            #logger.warning(xml_string)
            logger.warning(e)
            raise UserError(_(
                "The UBL XML file is not valid against the official "
                "XML Schema Definition. The XML file and the "
                "full error have been written in the server logs. "
                "Here is the error, which may give you an idea on the "
                "cause of the problem : %s.")
                % str(e))
        return True

    def _ubl_get_nsmap_namespace(self):
        nsmap = {
            None: 'urn:oasis:names:specification:ubl:schema:xsd:' + self.doc_name,
            'cac': 'urn:oasis:names:specification:ubl:'
                   'schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:'
                   'CommonBasicComponents-2',
            'ccts': 'urn:un:unece:uncefact:documentation:2',
            'ubltr': 'urn:oasis:names:specification:ubl:schema:xsd:TurkishCustomizationExtensionComponents',
            'xades': 'http://uri.etsi.org/01903/v1.3.2#',
            'udt': 'urn:un:unece:uncefact:data:specification:UnqualifiedDataTypesSchemaModule:2',
            'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
            'qdt': 'urn:oasis:names:specification:ubl:schema:xsd:QualifiedDatatypes-2',
            'ds': 'http://www.w3.org/2000/09/xmldsig#',
            'xsd': 'http://www.w3.org/2001/XMLSchema',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        }
        ns = {
            'cac': '{urn:oasis:names:specification:ubl:schema:xsd:'
                   'CommonAggregateComponents-2}',
            'cbc': '{urn:oasis:names:specification:ubl:schema:xsd:'
                   'CommonBasicComponents-2}',
        }
        return nsmap, ns
    
    def _create_ubl(self,parent_node):
        for var in vars(self.document): 
            if getattr(self.document,var):
                if getattr(self.document,var).alg_type:
                    self._createsub_ubl(parent_node,self.document,var)

    def _createsub_ubl(self, parent_node,obj1,element_name):
        if not getattr(obj1,element_name).alg_type:
            print("now")
        if getattr(obj1,element_name).alg_type not in ("list","list_wd","list_cbc"):
            if getattr(obj1,element_name).alg_is_activated:
                sub_element = etree.SubElement(parent_node, self.ns[getattr(obj1,element_name).alg_type] + element_name)
                if getattr(obj1,element_name).alg_type == "cbc":
                    
                    if getattr(obj1,element_name).alg_currencyID and getattr(obj1,element_name).alg_currencyID != "":
                        sub_element.set("currencyID",getattr(obj1,element_name).alg_currencyID)
                    if getattr(obj1,element_name).alg_unitCode and getattr(obj1,element_name).alg_unitCode != "":
                        sub_element.set("unitCode",getattr(obj1,element_name).alg_unitCode)
                    if getattr(obj1,element_name).alg_schemeID and getattr(obj1,element_name).alg_schemeID != "":
                        sub_element.set("schemeID",getattr(obj1,element_name).alg_schemeID)
                    try:
                        sub_element.text = getattr(obj1,element_name).value or ''
                    except Exception as e:
                        # if the validation of the XSD fails, we arrive here
                        logger = logging.getLogger(__name__)
                        logger.warning(
                            "The XML file is invalid against the XML Schema Definition")
                        #logger.warning(xml_string)
                        logger.warning(e)
                        raise UserError(_(
                            "The UBL XML file is not valid against the official "
                            "XML Schema Definition. The XML file and the "
                            "full error have been written in the server logs. "
                            "Here is the error, which may give you an idea on the "
                            "cause of the problem : %s.")
                            % str(e))
                else:
                    if getattr(obj1,element_name).alg_type == "cac":
                        for var in vars(getattr(obj1,element_name)): 
                            if not var.startswith("alg_"):
                                self._createsub_ubl(sub_element,getattr(obj1,element_name),var)
        if getattr(obj1,element_name).alg_type in ("list","list_wd","list_cbc") and not getattr(obj1,element_name).values == [] :
            if getattr(obj1,element_name).alg_type == "list":
                sub_element = etree.SubElement(parent_node, self.ns["cac"] + element_name)
            for row in getattr(obj1,element_name).values:
                liste = vars(row)
                if getattr(obj1,element_name).alg_type == "list_wd":
                    sub_element = etree.SubElement(parent_node, self.ns["cac"] + element_name)
                if getattr(obj1,element_name).alg_type == "list_cbc":
                    sub_element = etree.SubElement(parent_node, self.ns["cbc"] + element_name)
                    sub_element.text = row.value or ''
                for var in liste: 
                    if not var.startswith("alg_"):
                        self._createsub_ubl(sub_element,row,var)

class cbc(object):
    def __init__(self):
        self.alg_type = "cbc"
        self.alg_text = ""
        self.alg_currencyID = ""
        self.alg_schemeID = ""
        self.alg_unitCode = ""
        self.alg_is_activated = False

    @property
    def value(self):
        return self.alg_text

    @value.setter
    def value(self, val):    
        self.alg_text = val
        self.alg_is_activated = True

class cac(object):
    def __init__(self):
        self.alg_type = "cac"
        self.alg_text = ""
        self.alg_is_activated = False

class list_cls(object):
    def __init__(self,cls_name):
        self.alg_type = "list"
        self.alg_subclsname = cls_name
        self.values = []

class list_wd_cls(object):
    def __init__(self,cls_name):
        self.alg_type = "list_wd"
        self.alg_subclsname = cls_name
        self.values = []

class list_cbc_cls(object):
    def __init__(self,cls_name):
        self.alg_type = "list_cbc"
        self.alg_subclsname = cls_name
        self.values = []


class ornek_subcls(cac):
    def __init__(self):
        cac.__init__(self)
        self.col1 = cbc()
        self.col2 = cbc()


""" Seçimli(0..1): 
Zorunlu(1..n): 
Seçimli(0..1): 
Zorunlu(1): 
Seçimli(0..1): PhysicalLocation
Seçimli(0..1): PartyTaxScheme
Seçimli(0..n): PartyLegalEntity
Seçimli(0..1): Contact
Seçimli(0..1): Person
Seçimli(0..1): AgentParty
Tarafları (kurum ve şahıslar) 
">
<xsd:sequence>
(cac):\n\tdef __init__(self):\n\t\tcac.__init__(self):
"""


class CustomerParty(cac):
    def __init__(self):
        cac.__init__(self)
        self.Party = PartyType()
        self.DeliveryContact = list_cls("ContactType")

class Invoice(object):
    def __init__(self):
        self.UBLVersionID=cbc()
        self.CustomizationID=cbc()
        self.ProfileID=cbc()
        self.ID=cbc()
        self.CopyIndicator=cbc()
        self.UUID=cbc()
        self.IssueDate=cbc()
        self.IssueTime=cbc()
        self.InvoiceTypeCode=cbc()
        self.Note=list_cbc_cls("NoteType")
        self.DocumentCurrencyCode=cbc()
        self.TaxCurrencyCode=cbc()
        self.PricingCurrencyCode=cbc()
        self.PaymentCurrencyCode=cbc()
        self.PaymentAlternativeCurrencyCode=cbc()
        self.AccountingCost=cbc()
        self.LineCountNumeric=cbc()
        self.InvoicePeriod=list_cls("PeriodType")
        self.OrderReference=list_cls("OrderReferenceType")
        self.BillingReference=list_wd_cls("BillingReferenceType")
        self.DespatchDocumentReference=list_wd_cls("DocumentReferenceType")
        self.ReceiptDocumentReference=list_cls("DocumentReferenceType")
        self.OriginatorDocumentReference=list_cls("DocumentReferenceType")
        self.ContractDocumentReference=list_cls("DocumentReferenceType")
        self.AdditionalDocumentReference=list_wd_cls("DocumentReferenceType")
        self.Signature=list_cls("SignatureType")
        self.AccountingSupplierParty=list_cls("SupplierPartyType")
        self.AccountingCustomerParty=list_cls("CustomerPartyType")
        self.BuyerCustomerParty=list_cls("CustomerPartyType")
        self.SellerSupplierParty=list_cls("SupplierPartyType")
        self.TaxRepresentativeParty=list_cls("PartyType")
        self.Delivery=list_cls("DeliveryType")
        self.PaymentMeans=list_cls("PaymentMeansType")
        self.PaymentTerms=list_cls("PaymentTermsType")
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        self.TaxExchangeRate=list_cls("ExchangeRateType")
        self.PricingExchangeRate=list_cls("ExchangeRateType")
        self.PaymentExchangeRate=list_cls("ExchangeRateType")
        self.PaymentAlternativeExchangeRate=list_cls("ExchangeRateType")
        self.TaxTotal=list_cls("TaxTotalType")
        self.WithholdingTaxTotal=list_cls("TaxTotalType")
        self.LegalMonetaryTotal=list_cls("MonetaryTotalType")
        self.InvoiceLine=list_wd_cls("InvoiceLineType")

class Despatch(object):
    def __init__(self):
        self.UBLVersionID=cbc()
        self.CustomizationID=cbc()
        self.ProfileID=cbc()
        self.ID=cbc()
        self.CopyIndicator=cbc()
        self.UUID=cbc()
        self.IssueDate=cbc()
        self.IssueTime=cbc()
        self.DespatchAdviceTypeCode=cbc()
        self.Note=list_cbc_cls("NoteType")
        self.LineCountNumeric=cbc()
        self.OrderReference=list_cls("OrderReferenceType")
        self.AdditionalDocumentReference=list_cls("DocumentReferenceType")
        self.Signature=list_cls("SignatureType")
        self.DespatchSupplierParty=list_cls("SupplierPartyType")
        self.DeliveryCustomerParty=list_cls("CustomerPartyType")
        self.BuyerCustomerParty=list_cls("CustomerPartyType")
        self.SellerSupplierParty=list_cls("SupplierPartyType")
        self.OriginatorCustomerParty=list_cls("CustomerPartyType")
        self.Shipment=list_cls("ShipmentType")
        self.DespatchLine=list_wd_cls("DespatchLineType")

class ActivityDataLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.SupplyChainActivityTypeCode=cbc()
        self.BuyerCustomerParty=list_cls("CustomerPartyType")
        self.SellerSupplierParty=list_cls("SupplierPartyType")
        self.ActivityPeriod=list_cls("PeriodType")
        self.ActivityOriginLocation=list_cls("LocationType")
        self.ActivityFinalLocation=list_cls("LocationType")
        self.SalesItem=list_cls("SalesItemType")
        
        
class ActivityPropertyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        self.Value=cbc()
        
        
class AddressType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Postbox=cbc()
        self.Room=cbc()
        self.StreetName=cbc()
        self.BlockName=cbc()
        self.BuildingName=cbc()
        self.BuildingNumber=cbc()
        self.CitySubdivisionName=cbc()
        self.CityName=cbc()
        self.PostalZone=cbc()
        self.Region=cbc()
        self.District=cbc()
        self.Country=list_cls("CountryType")
        
        
class AddressLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Line=cbc()
        
        
class AirTransportType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AircraftID=cbc()
        
        
class AllowanceChargeType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ChargeIndicator=cbc()
        self.AllowanceChargeReason=cbc()
        self.MultiplierFactorNumeric=cbc()
        self.SequenceNumeric=cbc()
        self.Amount=cbc()
        self.BaseAmount=cbc()
        self.PerUnitAmount=cbc()

        def _set_amount(self,alg_currencyID,alg_text):
            self.Amount.alg_text = alg_text
            self.Amount.alg_currencyID = alg_currencyID
        
        
class AppealTermsType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Description=cbc()
        self.PresentationPeriod=list_cls("PeriodType")
        self.AppealInformationParty=list_cls("PartyType")
        self.AppealReceiverParty=list_cls("PartyType")
        self.MediationParty=list_cls("PartyType")
        
        
class AttachmentType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.EmbeddedDocumentBinaryObject=cbc()
        self.ExternalReference=list_cls("ExternalReferenceType")
        
        
class AuctionTermsType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AuctionConstraintIndicator=cbc()
        self.JustificationDescription=cbc()
        self.Description=cbc()
        self.ProcessDescription=cbc()
        self.ConditionsDescription=cbc()
        self.ElectronicDeviceDescription=cbc()
        self.AuctionURI=cbc()
        
        
class AwardingCriterionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.AwardingCriterionTypeCode=cbc()
        self.Description=cbc()
        self.WeightNumeric=cbc()
        self.Weight=cbc()
        self.CalculationExpression=cbc()
        self.CalculationExpressionCode=cbc()
        self.MinimumQuantity=cbc()
        self.MaximumQuantity=cbc()
        self.MinimumAmount=cbc()
        self.MaximumAmount=cbc()
        self.MinimumImprovementBid=cbc()
        self.SubordinateAwardingCriterion=list_cls("AwardingCriterionType")
        
        
class AwardingCriterionResponseType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.AwardingCriterionID=cbc()
        self.AwardingCriterionDescription=cbc()
        self.Description=cbc()
        self.Quantity=cbc()
        self.Amount=cbc()
        self.SubordinateAwardingCriterionResponse=list_cls("AwardingCriterionResponseType")
        
        
class AwardingTermsType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.WeightingAlgorithmCode=cbc()
        self.Description=cbc()
        self.TechnicalCommitteeDescription=cbc()
        self.LowTendersDescription=cbc()
        self.PrizeIndicator=cbc()
        self.PrizeDescription=cbc()
        self.PaymentDescription=cbc()
        self.FollowupContractIndicator=cbc()
        self.BindingOnBuyerIndicator=cbc()
        self.AwardingCriterion=list_cls("AwardingCriterionType")
        self.TechnicalCommitteePerson=list_cls("PersonType")
        
        
class BillingReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.InvoiceDocumentReference=list_cls("DocumentReferenceType")
        self.SelfBilledInvoiceDocumentReference=list_cls("DocumentReferenceType")
        self.CreditNoteDocumentReference=list_cls("DocumentReferenceType")
        self.SelfBilledCreditNoteDocumentReference=list_cls("DocumentReferenceType")
        self.DebitNoteDocumentReference=list_cls("DocumentReferenceType")
        self.ReminderDocumentReference=list_cls("DocumentReferenceType")
        self.AdditionalDocumentReference=list_cls("DocumentReferenceType")
        self.BillingReferenceLine=list_cls("BillingReferenceLineType")
        
        
class BillingReferenceLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Amount=cbc()
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        
        
class BranchType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        self.FinancialInstitution=list_cls("FinancialInstitutionType")
        
        
class BudgetAccountType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.BudgetYearNumeric=cbc()
        self.RequiredClassificationScheme=list_cls("ClassificationSchemeType")
        
        
class BudgetAccountLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.TotalAmount=cbc()
        self.BudgetAccount=list_cls("BudgetAccountType")
        
        
class CapabilityType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.CapabilityTypeCode=cbc()
        self.Description=cbc()
        self.ValueAmount=cbc()
        self.ValueQuantity=cbc()
        self.EvidenceSupplied=list_cls("EvidenceSuppliedType")
        self.ValidityPeriod=list_cls("PeriodType")
        
        
class CardAccountType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.PrimaryAccountNumberID=cbc()
        self.NetworkID=cbc()
        self.CardTypeCode=cbc()
        self.ValidityStartDate=cbc()
        self.ExpiryDate=cbc()
        self.IssuerID=cbc()
        self.IssueNumberID=cbc()
        self.CV2ID=cbc()
        self.CardChipCode=cbc()
        self.ChipApplicationID=cbc()
        self.HolderName=cbc()
        
        
class CatalogueItemSpecificationUpdateLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.ContractorCustomerParty=list_cls("CustomerPartyType")
        self.SellerSupplierParty=list_cls("SupplierPartyType")
        self.Item=list_cls("ItemType")
        
        
class CatalogueLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.ActionCode=cbc()
        self.LifeCycleStatusCode=cbc()
        self.ContractSubdivision=cbc()
        self.Note=cbc()
        self.OrderableIndicator=cbc()
        self.OrderableUnit=cbc()
        self.ContentUnitQuantity=cbc()
        self.OrderQuantityIncrementNumeric=cbc()
        self.MinimumOrderQuantity=cbc()
        self.MaximumOrderQuantity=cbc()
        self.WarrantyInformation=cbc()
        self.PackLevelCode=cbc()
        self.ContractorCustomerParty=list_cls("CustomerPartyType")
        self.SellerSupplierParty=list_cls("SupplierPartyType")
        self.WarrantyParty=list_cls("PartyType")
        self.WarrantyValidityPeriod=list_cls("PeriodType")
        self.LineValidityPeriod=list_cls("PeriodType")
        self.ItemComparison=list_cls("ItemComparisonType")
        self.ComponentRelatedItem=list_cls("RelatedItemType")
        self.AccessoryRelatedItem=list_cls("RelatedItemType")
        self.RequiredRelatedItem=list_cls("RelatedItemType")
        self.ReplacementRelatedItem=list_cls("RelatedItemType")
        self.ComplementaryRelatedItem=list_cls("RelatedItemType")
        self.ReplacedRelatedItem=list_cls("RelatedItemType")
        self.RequiredItemLocationQuantity=list_cls("ItemLocationQuantityType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.Item=list_cls("ItemType")
        self.KeywordItemProperty=list_cls("ItemPropertyType")
        self.CallForTendersLineReference=list_cls("LineReferenceType")
        self.CallForTendersDocumentReference=list_cls("DocumentReferenceType")
        
        
class CataloguePricingUpdateLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.ContractorCustomerParty=list_cls("CustomerPartyType")
        self.SellerSupplierParty=list_cls("SupplierPartyType")
        self.RequiredItemLocationQuantity=list_cls("ItemLocationQuantityType")
        
        
class CatalogueReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.UUID=cbc()
        self.IssueDate=cbc()
        self.IssueTime=cbc()
        self.RevisionDate=cbc()
        self.RevisionTime=cbc()
        self.Note=cbc()
        self.Description=cbc()
        self.VersionID=cbc()
        self.PreviousVersionID=cbc()
        
        
class CatalogueRequestLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.ContractSubdivision=cbc()
        self.Note=cbc()
        self.LineValidityPeriod=list_cls("PeriodType")
        self.RequiredItemLocationQuantity=list_cls("ItemLocationQuantityType")
        self.Item=list_cls("ItemType")
        
        
class CertificateType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.CertificateTypeCode=cbc()
        self.CertificateType=cbc()
        self.Remarks=cbc()
        self.IssuerParty=list_cls("PartyType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.Signature=list_cls("SignatureType")
        
        
class CertificateOfOriginApplicationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ReferenceID=cbc()
        self.CertificateType=cbc()
        self.ApplicationStatusCode=cbc()
        self.OriginalJobID=cbc()
        self.PreviousJobID=cbc()
        self.Remarks=cbc()
        self.Shipment=list_cls("ShipmentType")
        self.EndorserParty=list_cls("EndorserPartyType")
        self.PreparationParty=list_cls("PartyType")
        self.IssuerParty=list_cls("PartyType")
        self.ExporterParty=list_cls("PartyType")
        self.ImporterParty=list_cls("PartyType")
        self.IssuingCountry=list_cls("CountryType")
        self.DocumentDistribution=list_cls("DocumentDistributionType")
        self.SupportingDocumentReference=list_cls("DocumentReferenceType")
        self.Signature=list_cls("SignatureType")
        
        
class ClassificationCategoryType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        self.CodeValue=cbc()
        self.Description=cbc()
        self.CategorizesClassificationCategory=list_cls("ClassificationCategoryType")
        
        
class ClassificationSchemeType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.UUID=cbc()
        self.LastRevisionDate=cbc()
        self.LastRevisionTime=cbc()
        self.Note=cbc()
        self.Name=cbc()
        self.Description=cbc()
        self.AgencyID=cbc()
        self.AgencyName=cbc()
        self.VersionID=cbc()
        self.URI=cbc()
        self.SchemeURI=cbc()
        self.LanguageID=cbc()
        self.ClassificationCategory=list_cls("ClassificationCategoryType")
        
        
class ClauseType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Content=cbc()
        
        
class CommodityClassificationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ItemClassificationCode=cbc()
        
        
class CommunicationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ChannelCode=cbc()
        self.Channel=cbc()
        self.Value=cbc()
        
        
class CompletedTaskType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AnnualAverageAmount=cbc()
        self.TotalTaskAmount=cbc()
        self.PartyCapacityAmount=cbc()
        self.Description=cbc()
        self.EvidenceSupplied=list_cls("EvidenceSuppliedType")
        self.Period=list_cls("PeriodType")
        self.RecipientCustomerParty=list_cls("CustomerPartyType")
        
        
class ConditionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AttributeID=cbc()
        self.Measure=cbc()
        self.Description=cbc()
        self.MinimumMeasure=cbc()
        self.MaximumMeasure=cbc()
        
        
class ConsignmentType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.TotalInvoiceAmount=cbc()
        
        
class ConsumptionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.UtilityStatementTypeCode=cbc()
        self.MainPeriod=list_cls("PeriodType")
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        self.TaxTotal=list_cls("TaxTotalType")
        self.EnergyWaterSupply=list_cls("EnergyWaterSupplyType")
        self.TelecommunicationsSupply=list_cls("TelecommunicationsSupplyType")
        self.LegalMonetaryTotal=list_cls("MonetaryTotalType")
        
        
class ConsumptionAverageType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AverageAmount=cbc()
        self.Description=cbc()
        
        
class ConsumptionCorrectionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.CorrectionType=cbc()
        self.CorrectionTypeCode=cbc()
        self.MeterNumber=cbc()
        self.GasPressureQuantity=cbc()
        self.ActualTemperatureReductionQuantity=cbc()
        self.NormalTemperatureReductionQuantity=cbc()
        self.DifferenceTemperatureReductionQuantity=cbc()
        self.Description=cbc()
        self.CorrectionUnitAmount=cbc()
        self.ConsumptionEnergyQuantity=cbc()
        self.ConsumptionWaterQuantity=cbc()
        self.CorrectionAmount=cbc()
        
        
class ConsumptionHistoryType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.MeterNumber=cbc()
        self.Quantity=cbc()
        self.Amount=cbc()
        self.ConsumptionLevelCode=cbc()
        self.ConsumptionLevel=cbc()
        self.Description=cbc()
        self.Period=list_cls("PeriodType")
        
        
class ConsumptionLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.ParentDocumentLineReferenceID=cbc()
        self.InvoicedQuantity=cbc()
        self.LineExtensionAmount=cbc()
        self.Period=list_cls("PeriodType")
        self.Delivery=list_cls("DeliveryType")
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        self.TaxTotal=list_cls("TaxTotalType")
        self.UtilityItem=list_cls("UtilityItemType")
        self.Price=list_cls("PriceType")
        self.UnstructuredPrice=list_cls("UnstructuredPriceType")
        
        
class ConsumptionPointType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Description=cbc()
        self.SubscriberID=cbc()
        self.SubscriberType=cbc()
        self.SubscriberTypeCode=cbc()
        self.TotalDeliveredQuantity=cbc()
        self.Address=list_cls("AddressType")
        self.WebSiteAccess=list_cls("WebSiteAccessType")
        self.UtilityMeter=list_cls("MeterType")
        
        
class ConsumptionReportType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.ConsumptionType=cbc()
        self.ConsumptionTypeCode=cbc()
        self.Description=cbc()
        self.TotalConsumedQuantity=cbc()
        self.BasicConsumedQuantity=cbc()
        self.ResidentOccupantsNumeric=cbc()
        self.ConsumersEnergyLevelCode=cbc()
        self.ConsumersEnergyLevel=cbc()
        self.ResidenceType=cbc()
        self.ResidenceTypeCode=cbc()
        self.HeatingType=cbc()
        self.HeatingTypeCode=cbc()
        self.Period=list_cls("PeriodType")
        self.GuidanceDocumentReference=list_cls("DocumentReferenceType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.ConsumptionReportReference=list_cls("ConsumptionReportReferenceType")
        self.ConsumptionHistory=list_cls("ConsumptionHistoryType")
        
        
class ConsumptionReportReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ConsumptionReportID=cbc()
        self.ConsumptionType=cbc()
        self.ConsumptionTypeCode=cbc()
        self.TotalConsumedQuantity=cbc()
        self.Period=list_cls("PeriodType")
        
        
class ContactType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Name=cbc()
        self.Telephone=cbc()
        self.Telefax=cbc()
        self.ElectronicMail=cbc()
        self.Note=cbc()
        self.OtherCommunication=list_cls("CommunicationType")
        
        
class ContractType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.IssueDate=cbc()
        self.IssueTime=cbc()
        self.NominationDate=cbc()
        self.NominationTime=cbc()
        self.ContractTypeCode=cbc()
        self.ContractType=cbc()
        self.Note=cbc()
        self.VersionID=cbc()
        self.Description=cbc()
        self.ValidityPeriod=list_cls("PeriodType")
        self.ContractDocumentReference=list_cls("DocumentReferenceType")
        self.NominationPeriod=list_cls("PeriodType")
        self.ContractualDelivery=list_cls("DeliveryType")
        
        
class ContractExecutionRequirementType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        self.ExecutionRequirementCode=cbc()
        self.Description=cbc()
        
        
class ContractExtensionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.OptionsDescription=cbc()
        self.MinimumNumberNumeric=cbc()
        self.MaximumNumberNumeric=cbc()
        self.OptionValidityPeriod=list_cls("PeriodType")
        self.Renewal=list_cls("RenewalType")
        
        
class ContractingActivityType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ActivityTypeCode=cbc()
        self.ActivityType=cbc()
        
        
class ContractingPartyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.BuyerProfileURI=cbc()
        self.ContractingPartyType=list_cls("ContractingPartyTypeType")
        self.ContractingActivity=list_cls("ContractingActivityType")
        self.Party=list_cls("PartyType")
        
        
class ContractingPartyTypeType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.PartyTypeCode=cbc()
        self.PartyType=cbc()
        
        
class CorporateRegistrationSchemeType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Name=cbc()
        self.CorporateRegistrationTypeCode=cbc()
        self.JurisdictionRegionAddress=list_cls("AddressType")
        
        
class CountryType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.IdentificationCode=cbc()
        self.Name=cbc()
        
        
class CreditAccountType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AccountID=cbc()
        
        
class CreditNoteLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.UUID=cbc()
        self.Note=cbc()
        self.CreditedQuantity=cbc()
        self.LineExtensionAmount=cbc()
        self.TaxPointDate=cbc()
        self.AccountingCostCode=cbc()
        self.AccountingCost=cbc()
        self.PaymentPurposeCode=cbc()
        self.FreeOfChargeIndicator=cbc()
        self.InvoicePeriod=list_cls("PeriodType")
        self.OrderLineReference=list_cls("OrderLineReferenceType")
        self.DiscrepancyResponse=list_cls("ResponseType")
        self.DespatchLineReference=list_cls("LineReferenceType")
        self.ReceiptLineReference=list_cls("LineReferenceType")
        self.BillingReference=list_cls("BillingReferenceType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.PricingReference=list_cls("PricingReferenceType")
        self.OriginatorParty=list_cls("PartyType")
        self.Delivery=list_cls("DeliveryType")
        self.PaymentTerms=list_cls("PaymentTermsType")
        self.TaxTotal=list_cls("TaxTotalType")
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        self.Item=list_cls("ItemType")
        self.Price=list_cls("PriceType")
        self.DeliveryTerms=list_cls("DeliveryTermsType")
        self.SubCreditNoteLine=list_cls("CreditNoteLineType")
        self.ItemPriceExtension=list_cls("PriceExtensionType")
        
        
class CustomerPartyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Party=list_cls("PartyType")
        self.DeliveryContact=list_cls("ContactType")
        
        
class CustomsDeclarationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.IssuerParty=list_cls("PartyType")
        
        
class DebitNoteLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.UUID=cbc()
        self.Note=cbc()
        self.DebitedQuantity=cbc()
        self.LineExtensionAmount=cbc()
        self.TaxPointDate=cbc()
        self.AccountingCostCode=cbc()
        self.AccountingCost=cbc()
        self.PaymentPurposeCode=cbc()
        self.DiscrepancyResponse=list_cls("ResponseType")
        self.DespatchLineReference=list_cls("LineReferenceType")
        self.ReceiptLineReference=list_cls("LineReferenceType")
        self.BillingReference=list_cls("BillingReferenceType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.PricingReference=list_cls("PricingReferenceType")
        self.Delivery=list_cls("DeliveryType")
        self.TaxTotal=list_cls("TaxTotalType")
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        self.Item=list_cls("ItemType")
        self.Price=list_cls("PriceType")
        self.SubDebitNoteLine=list_cls("DebitNoteLineType")
        
        
class DeclarationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        self.DeclarationTypeCode=cbc()
        self.Description=cbc()
        self.EvidenceSupplied=list_cls("EvidenceSuppliedType")
        
        
class DeliveryType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Quantity=cbc()
        self.ActualDeliveryDate=cbc()
        self.ActualDeliveryTime=cbc()
        self.LatestDeliveryDate=cbc()
        self.LatestDeliveryTime=cbc()
        self.TrackingID=cbc()
        self.DeliveryAddress=list_cls("AddressType")
        self.AlternativeDeliveryLocation=list_cls("LocationType")
        self.EstimatedDeliveryPeriod=list_cls("PeriodType")
        self.CarrierParty=list_cls("PartyType")
        self.DeliveryParty=list_cls("PartyType")
        self.Despatch=list_cls("DespatchType")
        self.DeliveryTerms=list_cls("DeliveryTermsType")
        self.Shipment=list_cls("ShipmentType")
        
        
class DeliveryTermsType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.SpecialTerms=cbc()
        self.Amount=cbc()
        
        
class DeliveryUnitType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.BatchQuantity=cbc()
        self.ConsumerUnitQuantity=cbc()
        self.HazardousRiskIndicator=cbc()
        
        
class DependentPriceReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Percent=cbc()
        self.LocationAddress=list_cls("AddressType")
        self.DependentLineReference=list_cls("LineReferenceType")
        
class NoteType(cbc):		
    def __init__(self):		
        cbc.__init__(self)	

class DespatchType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.ActualDespatchDate=cbc()
        self.ActualDespatchTime=cbc()
        self.Instructions=cbc()
        self.DespatchAddress=list_cls("AddressType")
        self.DespatchParty=list_cls("PartyType")
        self.Contact=list_cls("ContactType")
        self.EstimatedDespatchPeriod=list_cls("PeriodType")
        
        
class DespatchLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=list_cbc_cls("NoteType")
        self.DeliveredQuantity=cbc()
        self.OutstandingQuantity=cbc()
        self.OutstandingReason=cbc()
        self.OversupplyQuantity=cbc()
        self.OrderLineReference=list_cls("OrderLineReferenceType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.Item=list_cls("ItemType")
        self.Shipment=list_cls("ShipmentType")
        
        
class DimensionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AttributeID=cbc()
        self.Measure=cbc()
        self.Description=cbc()
        self.MinimumMeasure=cbc()
        self.MaximumMeasure=cbc()
        
        
class DocumentDistributionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.PrintQualifier=cbc()
        self.MaximumCopiesNumeric=cbc()
        self.Party=list_cls("PartyType")
        
        
class DocumentReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.IssueDate=cbc()
        self.DocumentTypeCode=cbc()
        self.DocumentType=cbc()
        self.DocumentDescription=cbc()
        self.Attachment=list_cls("AttachmentType")
        self.ValidityPeriod=list_cls("PeriodType")
        self.IssuerParty=list_cls("PartyType")
        
        
class DocumentResponseType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Response=list_cls("ResponseType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.LineResponse=list_cls("LineResponseType")
        
        
class DutyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Amount=cbc()
        self.Duty=cbc()
        self.DutyCode=cbc()
        self.TaxCategory=list_cls("TaxCategoryType")
        
        
class EconomicOperatorRoleType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.RoleCode=cbc()
        self.RoleDescription=cbc()
        
        
class EconomicOperatorShortListType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.LimitationDescription=cbc()
        self.ExpectedQuantity=cbc()
        self.MaximumQuantity=cbc()
        self.MinimumQuantity=cbc()
        self.PreSelectedParty=list_cls("PartyType")
        
        
class EmissionCalculationMethodType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.CalculationMethodCode=cbc()
        self.FullnessIndicationCode=cbc()
        self.MeasurementFromLocation=list_cls("LocationType")
        self.MeasurementToLocation=list_cls("LocationType")
        
        
class EndorsementType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.DocumentID=cbc()
        self.ApprovalStatus=cbc()
        self.Remarks=cbc()
        self.EndorserParty=list_cls("EndorserPartyType")
        self.Signature=list_cls("SignatureType")
        
        
class EndorserPartyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.RoleCode=cbc()
        self.SequenceNumeric=cbc()
        self.Party=list_cls("PartyType")
        self.SignatoryContact=list_cls("ContactType")
        
        
class EnergyTaxReportType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TaxEnergyAmount=cbc()
        self.TaxEnergyOnAccountAmount=cbc()
        self.TaxEnergyBalanceAmount=cbc()
        self.TaxScheme=list_cls("TaxSchemeType")
        
        
class EnergyWaterSupplyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ConsumptionReport=list_cls("ConsumptionReportType")
        self.EnergyTaxReport=list_cls("EnergyTaxReportType")
        self.ConsumptionAverage=list_cls("ConsumptionAverageType")
        self.EnergyWaterConsumptionCorrection=list_cls("ConsumptionCorrectionType")
        
        
class EnvironmentalEmissionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.EnvironmentalEmissionTypeCode=cbc()
        self.ValueMeasure=cbc()
        self.Description=cbc()
        self.EmissionCalculationMethod=list_cls("EmissionCalculationMethodType")
        
        
class EvaluationCriterionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.EvaluationCriterionTypeCode=cbc()
        self.Description=cbc()
        self.ThresholdAmount=cbc()
        self.ThresholdQuantity=cbc()
        self.ExpressionCode=cbc()
        self.Expression=cbc()
        self.DurationPeriod=list_cls("PeriodType")
        self.SuggestedEvidence=list_cls("EvidenceType")
        
        
class EventType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.IdentificationID=cbc()
        self.OccurrenceDate=cbc()
        self.OccurrenceTime=cbc()
        self.TypeCode=cbc()
        self.Description=cbc()
        self.CompletionIndicator=cbc()
        self.CurrentStatus=list_cls("StatusType")
        self.Contact=list_cls("ContactType")
        self.OccurenceLocation=list_cls("LocationType")
        
        
class EventCommentType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Comment=cbc()
        self.IssueDate=cbc()
        self.IssueTime=cbc()
        
        
class EventLineItemType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.LineNumberNumeric=cbc()
        self.ParticipatingLocationsLocation=list_cls("LocationType")
        self.RetailPlannedImpact=list_cls("RetailPlannedImpactType")
        self.SupplyItem=list_cls("ItemType")
        
        
class EventTacticType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Comment=cbc()
        self.Quantity=cbc()
        self.EventTacticEnumeration=list_cls("EventTacticEnumerationType")
        self.Period=list_cls("PeriodType")
        
        
class EventTacticEnumerationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ConsumerIncentiveTacticTypeCode=cbc()
        self.DisplayTacticTypeCode=cbc()
        self.FeatureTacticTypeCode=cbc()
        self.TradeItemPackingLabelingTypeCode=cbc()
        
        
class EvidenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.EvidenceTypeCode=cbc()
        self.Description=cbc()
        self.CandidateStatement=cbc()
        self.EvidenceIssuingParty=list_cls("PartyType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.Language=list_cls("LanguageType")
        
        
class EvidenceSuppliedType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        
        
class ExceptionCriteriaLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.ThresholdValueComparisonCode=cbc()
        self.ThresholdQuantity=cbc()
        self.ExceptionStatusCode=cbc()
        self.CollaborationPriorityCode=cbc()
        self.ExceptionResolutionCode=cbc()
        self.SupplyChainActivityTypeCode=cbc()
        self.PerformanceMetricTypeCode=cbc()
        self.EffectivePeriod=list_cls("PeriodType")
        self.SupplyItem=list_cls("ItemType")
        self.ForecastExceptionCriterionLine=list_cls("ForecastExceptionCriterionLineType")
        
        
class ExceptionNotificationLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.Description=cbc()
        self.ExceptionStatusCode=cbc()
        self.CollaborationPriorityCode=cbc()
        self.ResolutionCode=cbc()
        self.ComparedValueMeasure=cbc()
        self.SourceValueMeasure=cbc()
        self.VarianceQuantity=cbc()
        self.SupplyChainActivityTypeCode=cbc()
        self.PerformanceMetricTypeCode=cbc()
        self.ExceptionObservationPeriod=list_cls("PeriodType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.ForecastException=list_cls("ForecastExceptionType")
        self.SupplyItem=list_cls("ItemType")
        
        
class ExchangeRateType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.SourceCurrencyCode=cbc()
        self.TargetCurrencyCode=cbc()
        self.CalculationRate=cbc()
        self.Date=cbc()
        
        
class ExternalReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.URI=cbc()
        
        
class FinancialAccountType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.CurrencyCode=cbc()
        self.PaymentNote=cbc()
        self.FinancialInstitutionBranch=list_cls("BranchType")
        
        
class FinancialGuaranteeType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.GuaranteeTypeCode=cbc()
        self.Description=cbc()
        self.LiabilityAmount=cbc()
        self.AmountRate=cbc()
        self.ConstitutionPeriod=list_cls("PeriodType")
        
        
class FinancialInstitutionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        
        
class ForecastExceptionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ForecastPurposeCode=cbc()
        self.ForecastTypeCode=cbc()
        self.IssueDate=cbc()
        self.IssueTime=cbc()
        self.DataSourceCode=cbc()
        self.ComparisonDataCode=cbc()
        self.ComparisonForecastIssueTime=cbc()
        self.ComparisonForecastIssueDate=cbc()
        
        
class ForecastExceptionCriterionLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ForecastPurposeCode=cbc()
        self.ForecastTypeCode=cbc()
        self.ComparisonDataSourceCode=cbc()
        self.DataSourceCode=cbc()
        self.TimeDeltaDaysQuantity=cbc()
        
        
class ForecastLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.FrozenDocumentIndicator=cbc()
        self.ForecastTypeCode=cbc()
        self.ForecastPeriod=list_cls("PeriodType")
        self.SalesItem=list_cls("SalesItemType")
        
        
class ForecastRevisionLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.Description=cbc()
        self.RevisedForecastLineID=cbc()
        self.SourceForecastIssueDate=cbc()
        self.SourceForecastIssueTime=cbc()
        self.AdjustmentReasonCode=cbc()
        self.ForecastPeriod=list_cls("PeriodType")
        self.SalesItem=list_cls("SalesItemType")
        
        
class FrameworkAgreementType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ExpectedOperatorQuantity=cbc()
        self.MaximumOperatorQuantity=cbc()
        self.Justification=cbc()
        self.Frequency=cbc()
        self.DurationPeriod=list_cls("PeriodType")
        self.SubsequentProcessTenderRequirement=list_cls("TenderRequirementType")
        
        
class GoodsItemType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Description=cbc()
        self.HazardousRiskIndicator=cbc()
        self.DeclaredCustomsValueAmount=cbc()
        self.DeclaredForCarriageValueAmount=cbc()
        self.DeclaredStatisticsValueAmount=cbc()
        self.FreeOnBoardValueAmount=cbc()
        self.InsuranceValueAmount=cbc()
        self.ValueAmount=cbc()
        self.GrossWeightMeasure=cbc()
        self.NetWeightMeasure=cbc()
        self.ChargeableWeightMeasure=cbc()
        self.GrossVolumeMeasure=cbc()
        self.NetVolumeMeasure=cbc()
        self.Quantity=cbc()
        self.RequiredCustomsID=cbc()
        self.CustomsStatusCode=cbc()
        self.CustomsTariffQuantity=cbc()
        self.CustomsImportClassifiedIndicator=cbc()
        self.ChargeableQuantity=cbc()
        self.ReturnableQuantity=cbc()
        self.TraceID=cbc()
        self.Item=list_cls("ItemType")
        self.FreightAllowanceCharge=list_cls("AllowanceChargeType")
        self.InvoiceLine=list_cls("InvoiceLineType")
        self.Temperature=list_cls("TemperatureType")
        self.OriginAddress=list_cls("AddressType")
        self.MeasurementDimension=list_cls("DimensionType")
        
        
class GoodsItemContainerType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Quantity=cbc()
        self.TransportEquipment=list_cls("TransportEquipmentType")
        
        
class HazardousGoodsTransitType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TransportEmergencyCardCode=cbc()
        self.PackingCriteriaCode=cbc()
        self.HazardousRegulationCode=cbc()
        self.InhalationToxicityZoneCode=cbc()
        self.TransportAuthorizationCode=cbc()
        self.MaximumTemperature=list_cls("TemperatureType")
        self.MinimumTemperature=list_cls("TemperatureType")
        
        
class HazardousItemType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.PlacardNotation=cbc()
        self.PlacardEndorsement=cbc()
        self.AdditionalInformation=cbc()
        self.UNDGCode=cbc()
        self.EmergencyProceduresCode=cbc()
        self.MedicalFirstAidGuideCode=cbc()
        self.TechnicalName=cbc()
        self.CategoryName=cbc()
        self.HazardousCategoryCode=cbc()
        self.UpperOrangeHazardPlacardID=cbc()
        self.LowerOrangeHazardPlacardID=cbc()
        self.MarkingID=cbc()
        self.HazardClassID=cbc()
        self.NetWeightMeasure=cbc()
        self.NetVolumeMeasure=cbc()
        self.Quantity=cbc()
        self.ContactParty=list_cls("PartyType")
        self.SecondaryHazard=list_cls("SecondaryHazardType")
        self.HazardousGoodsTransit=list_cls("HazardousGoodsTransitType")
        self.EmergencyTemperature=list_cls("TemperatureType")
        self.FlashpointTemperature=list_cls("TemperatureType")
        self.AdditionalTemperature=list_cls("TemperatureType")
        
        
class ImmobilizedSecurityType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ImmobilizationCertificateID=cbc()
        self.SecurityID=cbc()
        self.IssueDate=cbc()
        self.FaceValueAmount=cbc()
        self.MarketValueAmount=cbc()
        self.SharesNumberQuantity=cbc()
        self.IssuerParty=list_cls("PartyType")
        
        
class InstructionForReturnsLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.Quantity=cbc()
        self.ManufacturerParty=list_cls("PartyType")
        self.Item=list_cls("ItemType")
        
        
class InventoryReportLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.Quantity=cbc()
        self.InventoryValueAmount=cbc()
        self.AvailabilityDate=cbc()
        self.AvailabilityStatusCode=cbc()
        self.Item=list_cls("ItemType")
        self.InventoryLocation=list_cls("LocationType")
        
        
class InvoiceLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=list_cbc_cls("NoteType")
        self.InvoicedQuantity=cbc()
        self.LineExtensionAmount=cbc()
        self.OrderLineReference=list_cls("OrderLineReferenceType")
        self.DespatchLineReference=list_cls("LineReferenceType")
        self.ReceiptLineReference=list_cls("LineReferenceType")
        self.Delivery=list_cls("DeliveryType")
        self.AllowanceCharge=list_wd_cls("AllowanceChargeType")
        self.TaxTotal=list_cls("TaxTotalType")
        self.WithholdingTaxTotal=list_cls("TaxTotalType")
        self.Item=list_cls("ItemType")
        self.Price=list_cls("PriceType")
        self.SubInvoiceLine=list_cls("InvoiceLineType")
        
        
class ItemType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Description=cbc()
        self.Name=cbc()
        self.Keyword=cbc()
        self.BrandName=cbc()
        self.ModelName=cbc()
        self.BuyersItemIdentification=list_cls("ItemIdentificationType")
        self.SellersItemIdentification=list_cls("ItemIdentificationType")
        self.ManufacturersItemIdentification=list_cls("ItemIdentificationType")
        self.AdditionalItemIdentification=list_cls("ItemIdentificationType")
        self.OriginCountry=list_cbc_cls("CountryType")
        self.CommodityClassification=list_cbc_cls("CommodityClassificationType")
        self.ItemInstance=list_cls("ItemInstanceType")
        
        
class ItemComparisonType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.PriceAmount=cbc()
        self.Quantity=cbc()
        
        
class ItemIdentificationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        
        
class ItemInformationRequestLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TimeFrequencyCode=cbc()
        self.SupplyChainActivityTypeCode=cbc()
        self.ForecastTypeCode=cbc()
        self.PerformanceMetricTypeCode=cbc()
        self.Period=list_cls("PeriodType")
        self.SalesItem=list_cls("SalesItemType")
        
        
class ItemInstanceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ProductTraceID=cbc()
        self.ManufactureDate=cbc()
        self.ManufactureTime=cbc()
        self.BestBeforeDate=cbc()
        self.RegistrationID=cbc()
        self.SerialID=cbc()
        self.AdditionalItemProperty=list_cls("ItemPropertyType")
        self.LotIdentification=list_cls("LotIdentificationType")
        
        
class ItemLocationQuantityType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.LeadTimeMeasure=cbc()
        self.MinimumQuantity=cbc()
        self.MaximumQuantity=cbc()
        self.HazardousRiskIndicator=cbc()
        self.TradingRestrictions=cbc()
        self.ApplicableTerritoryAddress=list_cls("AddressType")
        self.Price=list_cls("PriceType")
        self.DeliveryUnit=list_cls("DeliveryUnitType")
        self.ApplicableTaxCategory=list_cls("TaxCategoryType")
        self.Package=list_cls("PackageType")
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        self.DependentPriceReference=list_cls("DependentPriceReferenceType")
        
        
class ItemManagementProfileType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.FrozenPeriodDaysNumeric=cbc()
        self.MinimumInventoryQuantity=cbc()
        self.MultipleOrderQuantity=cbc()
        self.OrderIntervalDaysNumeric=cbc()
        self.ReplenishmentOwnerDescription=cbc()
        self.TargetServicePercent=cbc()
        self.TargetInventoryQuantity=cbc()
        self.EffectivePeriod=list_cls("PeriodType")
        self.Item=list_cls("ItemType")
        self.ItemLocationQuantity=list_cls("ItemLocationQuantityType")
        
        
class ItemPropertyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Name=cbc()
        self.NameCode=cbc()
        self.TestMethod=cbc()
        self.Value=cbc()
        self.ValueQuantity=cbc()
        self.ValueQualifier=cbc()
        self.ImportanceCode=cbc()
        self.ListValue=cbc()
        self.UsabilityPeriod=list_cls("PeriodType")
        self.ItemPropertyGroup=list_cls("ItemPropertyGroupType")
        self.RangeDimension=list_cls("DimensionType")
        self.ItemPropertyRange=list_cls("ItemPropertyRangeType")
        
        
class ItemPropertyGroupType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Name=cbc()
        self.ImportanceCode=cbc()
        
        
class ItemPropertyRangeType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.MinimumValue=cbc()
        self.MaximumValue=cbc()
        
        
class LanguageType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Name=cbc()
        self.LocaleCode=cbc()
        
        
class LineItemType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.SalesOrderID=cbc()
        self.UUID=cbc()
        self.Note=cbc()
        self.LineStatusCode=cbc()
        self.Quantity=cbc()
        self.LineExtensionAmount=cbc()
        self.TotalTaxAmount=cbc()
        self.MinimumQuantity=cbc()
        self.MaximumQuantity=cbc()
        self.MinimumBackorderQuantity=cbc()
        self.MaximumBackorderQuantity=cbc()
        self.InspectionMethodCode=cbc()
        self.PartialDeliveryIndicator=cbc()
        self.BackOrderAllowedIndicator=cbc()
        self.AccountingCostCode=cbc()
        self.AccountingCost=cbc()
        self.WarrantyInformation=cbc()
        self.Delivery=list_cls("DeliveryType")
        self.DeliveryTerms=list_cls("DeliveryTermsType")
        self.OriginatorParty=list_cls("PartyType")
        self.OrderedShipment=list_cls("OrderedShipmentType")
        self.PricingReference=list_cls("PricingReferenceType")
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        self.Price=list_cls("PriceType")
        self.Item=list_cls("ItemType")
        self.SubLineItem=list_cls("LineItemType")
        self.WarrantyValidityPeriod=list_cls("PeriodType")
        self.WarrantyParty=list_cls("PartyType")
        self.TaxTotal=list_cls("TaxTotalType")
        self.ItemPriceExtension=list_cls("PriceExtensionType")
        self.LineReference=list_cls("LineReferenceType")
        
        
class LineReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.LineID=cbc()
        self.LineStatusCode=cbc()
        self.DocumentReference=list_cls("DocumentReferenceType")
        
        
class LineResponseType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.LineReference=list_cls("LineReferenceType")
        self.Response=list_cls("ResponseType")
        
        
class LocationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Address=list_cls("AddressType")
        
        
class LocationCoordinateType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.CoordinateSystemCode=cbc()
        self.LatitudeDegreesMeasure=cbc()
        self.LatitudeMinutesMeasure=cbc()
        self.LatitudeDirectionCode=cbc()
        self.LongitudeDegreesMeasure=cbc()
        self.LongitudeMinutesMeasure=cbc()
        self.LongitudeDirectionCode=cbc()
        self.AltitudeMeasure=cbc()
        
        
class LotIdentificationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.LotNumberID=cbc()
        self.ExpiryDate=cbc()
        self.AdditionalItemProperty=list_cls("ItemPropertyType")
        
        
class MaritimeTransportType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.VesselID=cbc()
        self.VesselName=cbc()
        self.RadioCallSignID=cbc()
        self.ShipsRequirements=cbc()
        self.GrossTonnageMeasure=cbc()
        self.NetTonnageMeasure=cbc()
        self.RegistryCertificateDocumentReference=list_cls("DocumentReferenceType")
        self.RegistryPortLocation=list_cls("LocationType")
        
        
class MeterType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.MeterNumber=cbc()
        self.MeterName=cbc()
        self.MeterConstant=cbc()
        self.MeterConstantCode=cbc()
        self.TotalDeliveredQuantity=cbc()
        self.MeterReading=list_cls("MeterReadingType")
        self.MeterProperty=list_cls("MeterPropertyType")
        
        
class MeterPropertyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        self.NameCode=cbc()
        self.Value=cbc()
        self.ValueQuantity=cbc()
        self.ValueQualifier=cbc()
        
        
class MeterReadingType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.MeterReadingType=cbc()
        self.MeterReadingTypeCode=cbc()
        self.PreviousMeterReadingDate=cbc()
        self.PreviousMeterQuantity=cbc()
        self.LatestMeterReadingDate=cbc()
        self.LatestMeterQuantity=cbc()
        self.PreviousMeterReadingMethod=cbc()
        self.PreviousMeterReadingMethodCode=cbc()
        self.LatestMeterReadingMethod=cbc()
        self.LatestMeterReadingMethodCode=cbc()
        self.MeterReadingComments=cbc()
        self.DeliveredQuantity=cbc()
        
        
class MiscellaneousEventType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.MiscellaneousEventTypeCode=cbc()
        self.EventLineItem=list_cls("EventLineItemType")
        
        
class MonetaryTotalType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.LineExtensionAmount=cbc()
        self.TaxExclusiveAmount=cbc()
        self.TaxInclusiveAmount=cbc()
        self.AllowanceTotalAmount=cbc()
        self.ChargeTotalAmount=cbc()
        self.PayableRoundingAmount=cbc()
        self.PayableAmount=cbc()
        
        
class NotificationRequirementType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.NotificationTypeCode=cbc()
        self.PostEventNotificationDurationMeasure=cbc()
        self.PreEventNotificationDurationMeasure=cbc()
        self.NotifyParty=list_cls("PartyType")
        self.NotificationPeriod=list_cls("PeriodType")
        self.NotificationLocation=list_cls("LocationType")
        
        
class OnAccountPaymentType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.EstimatedConsumedQuantity=cbc()
        self.Note=cbc()
        self.PaymentTerms=list_cls("PaymentTermsType")
        
        
class OrderLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.SubstitutionStatusCode=cbc()
        self.Note=cbc()
        self.LineItem=list_cls("LineItemType")
        self.SellerProposedSubstituteLineItem=list_cls("LineItemType")
        self.SellerSubstitutedLineItem=list_cls("LineItemType")
        self.BuyerProposedSubstituteLineItem=list_cls("LineItemType")
        self.CatalogueLineReference=list_cls("LineReferenceType")
        self.QuotationLineReference=list_cls("LineReferenceType")
        self.OrderLineReference=list_cls("OrderLineReferenceType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        
        
class OrderLineReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.LineID=cbc()
        self.SalesOrderLineID=cbc()
        self.UUID=cbc()
        self.LineStatusCode=cbc()
        self.OrderReference=list_cls("OrderReferenceType")
        
        
class OrderReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.SalesOrderID=cbc()
        self.IssueDate=cbc()
        self.OrderTypeCode=cbc()
        self.DocumentReference=list_cls("DocumentReferenceType")
        
        
class OrderedShipmentType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Shipment=list_cls("ShipmentType")
        self.Package=list_cls("PackageType")
        
        
class PackageType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Quantity=cbc()
        self.ReturnableMaterialIndicator=cbc()
        self.PackageLevelCode=cbc()
        self.PackagingTypeCode=cbc()
        self.PackingMaterial=cbc()
        self.ContainedPackage=list_cls("PackageType")
        self.GoodsItem=list_cls("GoodsItemType")
        self.MeasurementDimension=list_cls("DimensionType")
        
        
class PartyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.WebsiteURI=cbc()
        self.EndpointID=cbc()
        self.IndustryClassificationCode=cbc()
        self.PartyIdentification=list_wd_cls("PartyIdentificationType")
        self.PartyName= list_cls("PartyNameType")
        self.PostalAddress=list_cls("AddressType")
        self.PhysicalLocation=list_cls("LocationType")
        self.PartyTaxScheme=list_cls("PartyTaxSchemeType")
        self.PartyLegalEntity=list_cls("PartyLegalEntityType")
        self.Contact=list_cls("ContactType")
        self.Person=list_cls("PersonType")
        self.AgentParty=list_cls("PartyType")
        
        
class PartyIdentificationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        
        
class PartyLegalEntityType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.RegistrationName=cbc()
        self.CompanyID=cbc()
        self.RegistrationDate=cbc()
        self.SoleProprietorshipIndicator=cbc()
        self.CorporateStockAmount=cbc()
        self.FullyPaidSharesIndicator=cbc()
        self.CorporateRegistrationScheme=list_cls("CorporateRegistrationSchemeType")
        self.HeadOfficeParty=list_cls("PartyType")
        
        
class PartyNameType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        
        
class PartyTaxSchemeType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.RegistrationName=cbc()
        self.CompanyID=cbc()
        self.TaxScheme=list_cls("TaxSchemeType")
        
        
class PaymentType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.PaidAmount=cbc()
        self.ReceivedDate=cbc()
        self.PaidDate=cbc()
        self.PaidTime=cbc()
        self.InstructionID=cbc()
        
        
class PaymentMandateType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.MandateTypeCode=cbc()
        self.MaximumPaymentInstructionsNumeric=cbc()
        self.MaximumPaidAmount=cbc()
        self.SignatureID=cbc()
        self.PayerParty=list_cls("PartyType")
        self.PayerFinancialAccount=list_cls("FinancialAccountType")
        self.ValidityPeriod=list_cls("PeriodType")
        self.PaymentReversalPeriod=list_cls("PeriodType")
        self.Clause=list_cls("ClauseType")
        
        
class PaymentMeansType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.PaymentMeansCode=cbc()
        self.PaymentDueDate=cbc()
        self.PaymentChannelCode=cbc()
        self.InstructionNote=cbc()
        self.PayerFinancialAccount=list_cls("FinancialAccountType")
        self.PayeeFinancialAccount=list_cls("FinancialAccountType")
        
        
class PaymentTermsType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Note=cbc()
        self.PenaltySurchargePercent=cbc()
        self.Amount=cbc()
        self.PenaltyAmount=cbc()
        self.PaymentDueDate=cbc()
        self.SettlementPeriod=list_cls("PeriodType")
        
        
class PerformanceDataLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.PerformanceValueQuantity=cbc()
        self.PerformanceMetricTypeCode=cbc()
        self.Period=list_cls("PeriodType")
        self.Item=list_cls("ItemType")
        
        
class PeriodType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.StartDate=cbc()
        self.StartTime=cbc()
        self.EndDate=cbc()
        self.EndTime=cbc()
        self.DurationMeasure=cbc()
        self.Description=cbc()
        
        
class PersonType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.FirstName=cbc()
        self.FamilyName=cbc()
        self.Title=cbc()
        self.MiddleName=cbc()
        self.NameSuffix=cbc()
        self.NationalityID=cbc()
        self.FinancialAccount=list_cls("FinancialAccountType")
        self.IdentityDocumentReference=list_cls("DocumentReferenceType")
        
        
class PhysicalAttributeType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AttributeID=cbc()
        self.PositionCode=cbc()
        self.DescriptionCode=cbc()
        self.Description=cbc()
        
        
class PickupType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.ActualPickupDate=cbc()
        self.ActualPickupTime=cbc()
        self.EarliestPickupDate=cbc()
        self.EarliestPickupTime=cbc()
        self.LatestPickupDate=cbc()
        self.LatestPickupTime=cbc()
        self.PickupLocation=list_cls("LocationType")
        self.PickupParty=list_cls("PartyType")
        
        
class PowerOfAttorneyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.IssueDate=cbc()
        self.IssueTime=cbc()
        self.Description=cbc()
        self.NotaryParty=list_cls("PartyType")
        self.AgentParty=list_cls("PartyType")
        self.WitnessParty=list_cls("PartyType")
        self.MandateDocumentReference=list_cls("DocumentReferenceType")
        
        
class PriceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.PriceAmount=cbc()
        
        
class PriceExtensionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Amount=cbc()
        self.TaxTotal=list_cls("TaxTotalType")
        
        
class PriceListType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.StatusCode=cbc()
        self.ValidityPeriod=list_cls("PeriodType")
        self.PreviousPriceList=list_cls("PriceListType")
        
        
class PricingReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.OriginalItemLocationQuantity=list_cls("ItemLocationQuantityType")
        self.AlternativeConditionPrice=list_cls("PriceType")
        
        
class ProcessJustificationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.PreviousCancellationReasonCode=cbc()
        self.ProcessReasonCode=cbc()
        self.ProcessReason=cbc()
        self.Description=cbc()
        
        
class ProcurementProjectType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Name=cbc()
        self.Description=cbc()
        self.ProcurementTypeCode=cbc()
        self.ProcurementSubTypeCode=cbc()
        self.QualityControlCode=cbc()
        self.RequiredFeeAmount=cbc()
        self.FeeDescription=cbc()
        self.RequestedDeliveryDate=cbc()
        self.EstimatedOverallContractQuantity=cbc()
        self.Note=cbc()
        self.RequestedTenderTotal=list_cls("RequestedTenderTotalType")
        self.MainCommodityClassification=list_cls("CommodityClassificationType")
        self.AdditionalCommodityClassification=list_cls("CommodityClassificationType")
        self.RealizedLocation=list_cls("LocationType")
        self.PlannedPeriod=list_cls("PeriodType")
        self.ContractExtension=list_cls("ContractExtensionType")
        self.RequestForTenderLine=list_cls("RequestForTenderLineType")
        
        
class ProcurementProjectLotType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.TenderingTerms=list_cls("TenderingTermsType")
        self.ProcurementProject=list_cls("ProcurementProjectType")
        
        
class ProjectReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.UUID=cbc()
        self.IssueDate=cbc()
        self.WorkPhaseReference=list_cls("WorkPhaseReferenceType")
        
        
class PromotionalEventType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.PromotionalEventTypeCode=cbc()
        self.SubmissionDate=cbc()
        self.FirstShipmentAvailibilityDate=cbc()
        self.LatestProposalAcceptanceDate=cbc()
        self.PromotionalSpecification=list_cls("PromotionalSpecificationType")
        
        
class PromotionalEventLineItemType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Amount=cbc()
        self.EventLineItem=list_cls("EventLineItemType")
        
        
class PromotionalSpecificationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.SpecificationID=cbc()
        self.PromotionalEventLineItem=list_cls("PromotionalEventLineItemType")
        self.EventTactic=list_cls("EventTacticType")
        
        
class QualificationResolutionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AdmissionCode=cbc()
        self.ExclusionReason=cbc()
        self.Resolution=cbc()
        self.ResolutionDate=cbc()
        self.ResolutionTime=cbc()
        self.ProcurementProjectLot=list_cls("ProcurementProjectLotType")
        
        
class QualifyingPartyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ParticipationPercent=cbc()
        self.PersonalSituation=cbc()
        self.OperatingYearsQuantity=cbc()
        self.EmployeeQuantity=cbc()
        self.BusinessClassificationEvidenceID=cbc()
        self.BusinessIdentityEvidenceID=cbc()
        self.TendererRoleCode=cbc()
        self.BusinessClassificationScheme=list_cls("ClassificationSchemeType")
        self.TechnicalCapability=list_cls("CapabilityType")
        self.FinancialCapability=list_cls("CapabilityType")
        self.CompletedTask=list_cls("CompletedTaskType")
        self.Declaration=list_cls("DeclarationType")
        self.Party=list_cls("PartyType")
        self.EconomicOperatorRole=list_cls("EconomicOperatorRoleType")
        
        
class QuotationLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.Quantity=cbc()
        self.LineExtensionAmount=cbc()
        self.TotalTaxAmount=cbc()
        self.RequestForQuotationLineID=cbc()
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.LineItem=list_cls("LineItemType")
        self.SellerProposedSubstituteLineItem=list_cls("LineItemType")
        self.AlternativeLineItem=list_cls("LineItemType")
        self.RequestLineReference=list_cls("LineReferenceType")
        
        
class RailTransportType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TrainID=cbc()
        self.RailCarID=cbc()
        
        
class ReceiptLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.ReceivedQuantity=cbc()
        self.ShortQuantity=cbc()
        self.RejectedQuantity=cbc()
        self.RejectReasonCode=cbc()
        self.RejectReason=cbc()
        self.OversupplyQuantity=cbc()
        self.ReceivedDate=cbc()
        self.TimingComplaintCode=cbc()
        self.TimingComplaint=cbc()
        self.OrderLineReference=list_cls("OrderLineReferenceType")
        self.DespatchLineReference=list_cls("LineReferenceType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.Item=list_cls("ItemType")
        self.Shipment=list_cls("ShipmentType")
        
        
class RegulationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        self.LegalReference=cbc()
        self.OntologyURI=cbc()
        
        
class RelatedItemType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Quantity=cbc()
        self.Description=cbc()
        
        
class ReminderLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.UUID=cbc()
        self.BalanceBroughtForwardIndicator=cbc()
        self.DebitLineAmount=cbc()
        self.CreditLineAmount=cbc()
        self.AccountingCostCode=cbc()
        self.AccountingCost=cbc()
        self.PenaltySurchargePercent=cbc()
        self.Amount=cbc()
        self.PaymentPurposeCode=cbc()
        self.ReminderPeriod=list_cls("PeriodType")
        self.BillingReference=list_cls("BillingReferenceType")
        self.ExchangeRate=list_cls("ExchangeRateType")
        
        
class RemittanceAdviceLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.UUID=cbc()
        self.DebitLineAmount=cbc()
        self.CreditLineAmount=cbc()
        self.BalanceAmount=cbc()
        self.PaymentPurposeCode=cbc()
        self.InvoicingPartyReference=cbc()
        self.AccountingSupplierParty=list_cls("SupplierPartyType")
        self.AccountingCustomerParty=list_cls("CustomerPartyType")
        self.BuyerCustomerParty=list_cls("CustomerPartyType")
        self.SellerSupplierParty=list_cls("SupplierPartyType")
        self.OriginatorCustomerParty=list_cls("CustomerPartyType")
        self.PayeeParty=list_cls("PartyType")
        self.InvoicePeriod=list_cls("PeriodType")
        self.BillingReference=list_cls("BillingReferenceType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.ExchangeRate=list_cls("ExchangeRateType")
        
        
class RenewalType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Amount=cbc()
        self.Period=list_cls("PeriodType")
        
        
class RequestForQuotationLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.UUID=cbc()
        self.Note=cbc()
        self.OptionalLineItemIndicator=cbc()
        self.PrivacyCode=cbc()
        self.SecurityClassificationCode=cbc()
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.LineItem=list_cls("LineItemType")
        
        
class RequestForTenderLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.UUID=cbc()
        self.Note=cbc()
        self.Quantity=cbc()
        self.MinimumQuantity=cbc()
        self.MaximumQuantity=cbc()
        self.TaxIncludedIndicator=cbc()
        self.MinimumAmount=cbc()
        self.MaximumAmount=cbc()
        self.EstimatedAmount=cbc()
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.DeliveryPeriod=list_cls("PeriodType")
        self.RequiredItemLocationQuantity=list_cls("ItemLocationQuantityType")
        self.WarrantyValidityPeriod=list_cls("PeriodType")
        self.Item=list_cls("ItemType")
        self.SubRequestForTenderLine=list_cls("RequestForTenderLineType")
        
        
class RequestedTenderTotalType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.EstimatedOverallContractAmount=cbc()
        self.TotalAmount=cbc()
        self.TaxIncludedIndicator=cbc()
        self.MinimumAmount=cbc()
        self.MaximumAmount=cbc()
        self.MonetaryScope=cbc()
        self.AverageSubsequentContractAmount=cbc()
        self.ApplicableTaxCategory=list_cls("TaxCategoryType")
        
        
class ResponseType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ReferenceID=cbc()
        self.ResponseCode=cbc()
        self.Description=cbc()
        
        
class ResultOfVerificationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ValidatorID=cbc()
        self.ValidationResultCode=cbc()
        self.ValidationDate=cbc()
        self.ValidationTime=cbc()
        self.ValidateProcess=cbc()
        self.ValidateTool=cbc()
        self.ValidateToolVersion=cbc()
        self.SignatoryParty=list_cls("PartyType")
        
        
class RetailPlannedImpactType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Amount=cbc()
        self.ForecastPurposeCode=cbc()
        self.ForecastTypeCode=cbc()
        self.Period=list_cls("PeriodType")
        
        
class RoadTransportType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.LicensePlateID=cbc()
        
        
class SalesItemType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Quantity=cbc()
        self.ActivityProperty=list_cls("ActivityPropertyType")
        self.TaxExclusivePrice=list_cls("PriceType")
        self.TaxInclusivePrice=list_cls("PriceType")
        self.Item=list_cls("ItemType")
        
        
class SecondaryHazardType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.PlacardNotation=cbc()
        self.PlacardEndorsement=cbc()
        self.EmergencyProceduresCode=cbc()
        self.Extension=cbc()
        
        
class ServiceFrequencyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.WeekDayCode=cbc()
        
        
class ServiceProviderPartyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.ServiceTypeCode=cbc()
        self.ServiceType=cbc()
        self.Party=list_cls("PartyType")
        self.SellerContact=list_cls("ContactType")
        
        
class ShareholderPartyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.PartecipationPercent=cbc()
        self.Party=list_cls("PartyType")
        
        
class ShipmentType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.HandlingCode=cbc()
        self.HandlingInstructions=cbc()
        self.GrossWeightMeasure=cbc()
        self.NetWeightMeasure=cbc()
        self.GrossVolumeMeasure=cbc()
        self.NetVolumeMeasure=cbc()
        self.TotalGoodsItemQuantity=cbc()
        self.TotalTransportHandlingUnitQuantity=cbc()
        self.InsuranceValueAmount=cbc()
        self.DeclaredCustomsValueAmount=cbc()
        self.DeclaredForCarriageValueAmount=cbc()
        self.DeclaredStatisticsValueAmount=cbc()
        self.FreeOnBoardValueAmount=cbc()
        self.SpecialInstructions=cbc()
        self.GoodsItem=list_cls("GoodsItemType")
        self.ShipmentStage=list_cls("ShipmentStageType")
        self.Delivery=list_cls("DeliveryType")
        self.TransportHandlingUnit=list_cls("TransportHandlingUnitType")
        self.ReturnAddress=list_cls("AddressType")
        self.FirstArrivalPortLocation=list_cls("LocationType")
        self.LastExitPortLocation=list_cls("LocationType")
        
        
class ShipmentStageType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.TransportModeCode=cbc()
        self.TransportMeansTypeCode=cbc()
        self.TransitDirectionCode=cbc()
        self.Instructions=cbc()
        self.TransitPeriod=list_cls("PeriodType")
        self.TransportMeans=list_cls("TransportMeansType")
        self.DriverPerson=list_cls("PersonType")
        
        
class SignatureType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.SignatoryParty=list_cls("PartyType")
        self.DigitalSignatureAttachment=list_cls("AttachmentType")
        
        
class StatementLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.UUID=cbc()
        self.BalanceBroughtForwardIndicator=cbc()
        self.DebitLineAmount=cbc()
        self.CreditLineAmount=cbc()
        self.BalanceAmount=cbc()
        self.PaymentPurposeCode=cbc()
        self.PaymentMeans=list_cls("PaymentMeansType")
        self.PaymentTerms=list_cls("PaymentTermsType")
        self.BuyerCustomerParty=list_cls("CustomerPartyType")
        self.SellerSupplierParty=list_cls("SupplierPartyType")
        self.OriginatorCustomerParty=list_cls("CustomerPartyType")
        self.AccountingCustomerParty=list_cls("CustomerPartyType")
        self.AccountingSupplierParty=list_cls("SupplierPartyType")
        self.PayeeParty=list_cls("PartyType")
        self.InvoicePeriod=list_cls("PeriodType")
        self.BillingReference=list_cls("BillingReferenceType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.ExchangeRate=list_cls("ExchangeRateType")
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        self.CollectedPayment=list_cls("PaymentType")
        
        
class StatusType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ConditionCode=cbc()
        self.ReferenceDate=cbc()
        self.ReferenceTime=cbc()
        self.Description=cbc()
        self.StatusReasonCode=cbc()
        self.StatusReason=cbc()
        self.SequenceID=cbc()
        self.Text=cbc()
        self.IndicationIndicator=cbc()
        self.Percent=cbc()
        self.ReliabilityPercent=cbc()
        self.Condition=list_cls("ConditionType")
        
        
class StockAvailabilityReportLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.Quantity=cbc()
        self.ValueAmount=cbc()
        self.AvailabilityDate=cbc()
        self.AvailabilityStatusCode=cbc()
        self.Item=list_cls("ItemType")
        
        
class StowageType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.LocationID=cbc()
        self.Location=cbc()
        self.MeasurementDimension=list_cls("DimensionType")
        
        
class SubcontractTermsType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Rate=cbc()
        self.UnknownPriceIndicator=cbc()
        self.Description=cbc()
        self.Amount=cbc()
        self.SubcontractingConditionsCode=cbc()
        self.MaximumPercent=cbc()
        self.MinimumPercent=cbc()
        
        
class SubscriberConsumptionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ConsumptionID=cbc()
        self.SpecificationTypeCode=cbc()
        self.Note=cbc()
        self.TotalMeteredQuantity=cbc()
        self.SubscriberParty=list_cls("PartyType")
        self.UtilityConsumptionPoint=list_cls("ConsumptionPointType")
        self.OnAccountPayment=list_cls("OnAccountPaymentType")
        self.Consumption=list_cls("ConsumptionType")
        self.SupplierConsumption=list_cls("SupplierConsumptionType")
        
        
class SupplierConsumptionType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Description=cbc()
        self.UtilitySupplierParty=list_cls("PartyType")
        self.UtilityCustomerParty=list_cls("PartyType")
        self.Consumption=list_cls("ConsumptionType")
        self.Contract=list_cls("ContractType")
        self.ConsumptionLine=list_cls("ConsumptionLineType")
        
        
class SupplierPartyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Party=list_cls("PartyType")
        self.DespatchContact=list_cls("ContactType")
        
        
class TaxCategoryType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        self.TaxExemptionReasonCode=cbc()
        self.TaxExemptionReason=cbc()
        self.TaxScheme=list_cls("TaxSchemeType")
        
        
class TaxSchemeType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Name=cbc()
        self.TaxTypeCode=cbc()
        
        
class TaxSubtotalType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TaxableAmount=cbc()
        self.TaxAmount=cbc()
        self.CalculationSequenceNumeric=cbc()
        self.TransactionCurrencyTaxAmount=cbc()
        self.Percent=cbc()
        self.BaseUnitMeasure=cbc()
        self.PerUnitAmount=cbc()
        self.TaxCategory=list_cls("TaxCategoryType")
        
        
class TaxTotalType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TaxAmount=cbc()
        self.TaxSubtotal=list_wd_cls("TaxSubtotalType")
        
        
class TelecommunicationsServiceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.CallDate=cbc()
        self.CallTime=cbc()
        self.ServiceNumberCalled=cbc()
        self.TelecommunicationsServiceCategory=cbc()
        self.TelecommunicationsServiceCategoryCode=cbc()
        self.MovieTitle=cbc()
        self.RoamingPartnerName=cbc()
        self.PayPerView=cbc()
        self.Quantity=cbc()
        self.TelecommunicationsServiceCall=cbc()
        self.TelecommunicationsServiceCallCode=cbc()
        self.CallBaseAmount=cbc()
        self.CallExtensionAmount=cbc()
        self.Price=list_cls("PriceType")
        self.Country=list_cls("CountryType")
        self.ExchangeRate=list_cls("ExchangeRateType")
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        self.TaxTotal=list_cls("TaxTotalType")
        self.CallDuty=list_cls("DutyType")
        self.TimeDuty=list_cls("DutyType")
        
        
class TelecommunicationsSupplyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TelecommunicationsSupplyType=cbc()
        self.TelecommunicationsSupplyTypeCode=cbc()
        self.PrivacyCode=cbc()
        self.Description=cbc()
        self.TotalAmount=cbc()
        self.TelecommunicationsSupplyLine=list_cls("TelecommunicationsSupplyLineType")
        
        
class TelecommunicationsSupplyLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.PhoneNumber=cbc()
        self.Description=cbc()
        self.LineExtensionAmount=cbc()
        self.ExchangeRate=list_cls("ExchangeRateType")
        self.AllowanceCharge=list_cls("AllowanceChargeType")
        self.TaxTotal=list_cls("TaxTotalType")
        self.TelecommunicationsService=list_cls("TelecommunicationsServiceType")
        
        
class TemperatureType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AttributeID=cbc()
        self.Measure=cbc()
        self.Description=cbc()
        
        
class TenderLineType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.Note=cbc()
        self.Quantity=cbc()
        self.LineExtensionAmount=cbc()
        self.TotalTaxAmount=cbc()
        self.OrderableUnit=cbc()
        self.ContentUnitQuantity=cbc()
        self.OrderQuantityIncrementNumeric=cbc()
        self.MinimumOrderQuantity=cbc()
        self.MaximumOrderQuantity=cbc()
        self.WarrantyInformation=cbc()
        self.PackLevelCode=cbc()
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.Item=list_cls("ItemType")
        self.OfferedItemLocationQuantity=list_cls("ItemLocationQuantityType")
        self.ReplacementRelatedItem=list_cls("RelatedItemType")
        self.WarrantyParty=list_cls("PartyType")
        self.WarrantyValidityPeriod=list_cls("PeriodType")
        self.SubTenderLine=list_cls("TenderLineType")
        self.CallForTendersLineReference=list_cls("LineReferenceType")
        self.CallForTendersDocumentReference=list_cls("DocumentReferenceType")
        
        
class TenderPreparationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TenderEnvelopeID=cbc()
        self.TenderEnvelopeTypeCode=cbc()
        self.Description=cbc()
        self.OpenTenderID=cbc()
        self.ProcurementProjectLot=list_cls("ProcurementProjectLotType")
        self.DocumentTenderRequirement=list_cls("TenderRequirementType")
        
        
class TenderRequirementType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        self.Description=cbc()
        self.TemplateDocumentReference=list_cls("DocumentReferenceType")
        
        
class TenderResultType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TenderResultCode=cbc()
        self.Description=cbc()
        self.AdvertisementAmount=cbc()
        self.AwardDate=cbc()
        self.AwardTime=cbc()
        self.ReceivedTenderQuantity=cbc()
        self.LowerTenderAmount=cbc()
        self.HigherTenderAmount=cbc()
        self.StartDate=cbc()
        self.ReceivedElectronicTenderQuantity=cbc()
        self.ReceivedForeignTenderQuantity=cbc()
        self.Contract=list_cls("ContractType")
        self.AwardedTenderedProject=list_cls("TenderedProjectType")
        self.ContractFormalizationPeriod=list_cls("PeriodType")
        self.SubcontractTerms=list_cls("SubcontractTermsType")
        self.WinningParty=list_cls("WinningPartyType")
        
        
class TenderedProjectType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.VariantID=cbc()
        self.FeeAmount=cbc()
        self.FeeDescription=cbc()
        self.TenderEnvelopeID=cbc()
        self.TenderEnvelopeTypeCode=cbc()
        self.ProcurementProjectLot=list_cls("ProcurementProjectLotType")
        self.EvidenceDocumentReference=list_cls("DocumentReferenceType")
        self.TaxTotal=list_cls("TaxTotalType")
        self.LegalMonetaryTotal=list_cls("MonetaryTotalType")
        self.TenderLine=list_cls("TenderLineType")
        self.AwardingCriterionResponse=list_cls("AwardingCriterionResponseType")
        
        
class TendererPartyQualificationType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.InterestedProcurementProjectLot=list_cls("ProcurementProjectLotType")
        self.MainQualifyingParty=list_cls("QualifyingPartyType")
        self.AdditionalQualifyingParty=list_cls("QualifyingPartyType")
        
        
class TendererQualificationRequestType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.CompanyLegalFormCode=cbc()
        self.CompanyLegalForm=cbc()
        self.PersonalSituation=cbc()
        self.OperatingYearsQuantity=cbc()
        self.EmployeeQuantity=cbc()
        self.Description=cbc()
        self.RequiredBusinessClassificationScheme=list_cls("ClassificationSchemeType")
        self.TechnicalEvaluationCriterion=list_cls("EvaluationCriterionType")
        self.FinancialEvaluationCriterion=list_cls("EvaluationCriterionType")
        self.SpecificTendererRequirement=list_cls("TendererRequirementType")
        self.EconomicOperatorRole=list_cls("EconomicOperatorRoleType")
        
        
class TendererRequirementType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Name=cbc()
        self.TendererRequirementTypeCode=cbc()
        self.Description=cbc()
        self.LegalReference=cbc()
        self.SuggestedEvidence=list_cls("EvidenceType")
        
        
class TenderingProcessType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.OriginalContractingSystemID=cbc()
        self.Description=cbc()
        self.NegotiationDescription=cbc()
        self.ProcedureCode=cbc()
        self.UrgencyCode=cbc()
        self.ExpenseCode=cbc()
        self.PartPresentationCode=cbc()
        self.ContractingSystemCode=cbc()
        self.SubmissionMethodCode=cbc()
        self.CandidateReductionConstraintIndicator=cbc()
        self.GovernmentAgreementConstraintIndicator=cbc()
        self.DocumentAvailabilityPeriod=list_cls("PeriodType")
        self.TenderSubmissionDeadlinePeriod=list_cls("PeriodType")
        self.InvitationSubmissionPeriod=list_cls("PeriodType")
        self.ParticipationRequestReceptionPeriod=list_cls("PeriodType")
        self.NoticeDocumentReference=list_cls("DocumentReferenceType")
        self.AdditionalDocumentReference=list_cls("DocumentReferenceType")
        self.ProcessJustification=list_cls("ProcessJustificationType")
        self.EconomicOperatorShortList=list_cls("EconomicOperatorShortListType")
        self.OpenTenderEvent=list_cls("EventType")
        self.AuctionTerms=list_cls("AuctionTermsType")
        self.FrameworkAgreement=list_cls("FrameworkAgreementType")
        
        
class TenderingTermsType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.AwardingMethodTypeCode=cbc()
        self.PriceEvaluationCode=cbc()
        self.MaximumVariantQuantity=cbc()
        self.VariantConstraintIndicator=cbc()
        self.AcceptedVariantsDescription=cbc()
        self.PriceRevisionFormulaDescription=cbc()
        self.FundingProgramCode=cbc()
        self.FundingProgram=cbc()
        self.MaximumAdvertisementAmount=cbc()
        self.Note=cbc()
        self.PaymentFrequencyCode=cbc()
        self.EconomicOperatorRegistryURI=cbc()
        self.RequiredCurriculaIndicator=cbc()
        self.OtherConditionsIndicator=cbc()
        self.AdditionalConditions=cbc()
        self.LatestSecurityClearanceDate=cbc()
        self.DocumentationFeeAmount=cbc()
        self.PenaltyClause=list_cls("ClauseType")
        self.RequiredFinancialGuarantee=list_cls("FinancialGuaranteeType")
        self.ProcurementLegislationDocumentReference=list_cls("DocumentReferenceType")
        self.FiscalLegislationDocumentReference=list_cls("DocumentReferenceType")
        self.EnvironmentalLegislationDocumentReference=list_cls("DocumentReferenceType")
        self.EmploymentLegislationDocumentReference=list_cls("DocumentReferenceType")
        self.ContractualDocumentReference=list_cls("DocumentReferenceType")
        self.CallForTendersDocumentReference=list_cls("DocumentReferenceType")
        self.WarrantyValidityPeriod=list_cls("PeriodType")
        self.PaymentTerms=list_cls("PaymentTermsType")
        self.TendererQualificationRequest=list_cls("TendererQualificationRequestType")
        self.AllowedSubcontractTerms=list_cls("SubcontractTermsType")
        self.TenderPreparation=list_cls("TenderPreparationType")
        self.ContractExecutionRequirement=list_cls("ContractExecutionRequirementType")
        self.AwardingTerms=list_cls("AwardingTermsType")
        self.AdditionalInformationParty=list_cls("PartyType")
        self.DocumentProviderParty=list_cls("PartyType")
        self.TenderRecipientParty=list_cls("PartyType")
        self.ContractResponsibleParty=list_cls("PartyType")
        self.TenderEvaluationParty=list_cls("PartyType")
        self.TenderValidityPeriod=list_cls("PeriodType")
        self.ContractAcceptancePeriod=list_cls("PeriodType")
        self.AppealTerms=list_cls("AppealTermsType")
        self.Language=list_cls("LanguageType")
        self.BudgetAccountLine=list_cls("BudgetAccountLineType")
        self.ReplacedNoticeDocumentReference=list_cls("DocumentReferenceType")
        
        
class TradeFinancingType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.FinancingInstrumentCode=cbc()
        self.ContractDocumentReference=list_cls("DocumentReferenceType")
        self.DocumentReference=list_cls("DocumentReferenceType")
        self.FinancingParty=list_cls("PartyType")
        self.FinancingFinancialAccount=list_cls("FinancialAccountType")
        self.Clause=list_cls("ClauseType")
        
        
class TradingTermsType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Information=cbc()
        self.Reference=cbc()
        self.ApplicableAddress=list_cls("AddressType")
        
        
class TransactionConditionsType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.ActionCode=cbc()
        self.Description=cbc()
        self.DocumentReference=list_cls("DocumentReferenceType")
        
        
class TransportEquipmentType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.TransportEquipmentTypeCode=cbc()
        self.Description=cbc()
        
        
class TransportEquipmentSealType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.SealIssuerTypeCode=cbc()
        self.Condition=cbc()
        self.SealStatusCode=cbc()
        self.SealingPartyType=cbc()
        
        
class TransportEventType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.IdentificationID=cbc()
        self.OccurrenceDate=cbc()
        self.OccurrenceTime=cbc()
        self.TransportEventTypeCode=cbc()
        self.Description=cbc()
        self.CompletionIndicator=cbc()
        self.ReportedShipment=list_cls("ShipmentType")
        self.CurrentStatus=list_cls("StatusType")
        self.Contact=list_cls("ContactType")
        self.Location=list_cls("LocationType")
        self.Signature=list_cls("SignatureType")
        self.Period=list_cls("PeriodType")
        
        
class TransportExecutionTermsType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TransportUserSpecialTerms=cbc()
        self.TransportServiceProviderSpecialTerms=cbc()
        self.ChangeConditions=cbc()
        self.PaymentTerms=list_cls("PaymentTermsType")
        self.DeliveryTerms=list_cls("DeliveryTermsType")
        self.BonusPaymentTerms=list_cls("PaymentTermsType")
        self.CommissionPaymentTerms=list_cls("PaymentTermsType")
        self.PenaltyPaymentTerms=list_cls("PaymentTermsType")
        self.EnvironmentalEmission=list_cls("EnvironmentalEmissionType")
        self.NotificationRequirement=list_cls("NotificationRequirementType")
        self.ServiceChargePaymentTerms=list_cls("PaymentTermsType")
        
        
class TransportHandlingUnitType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.TransportHandlingUnitTypeCode=cbc()
        self.HandlingCode=cbc()
        self.HandlingInstructions=cbc()
        self.HazardousRiskIndicator=cbc()
        self.TotalGoodsItemQuantity=cbc()
        self.TotalPackageQuantity=cbc()
        self.DamageRemarks=cbc()
        self.TraceID=cbc()
        self.ActualPackage=list_cls("PackageType")
        self.TransportEquipment=list_wd_cls("TransportEquipmentType")
        self.TransportMeans=list_cls("TransportMeansType")
        self.HazardousGoodsTransit=list_cls("HazardousGoodsTransitType")
        self.MeasurementDimension=list_cls("DimensionType")
        self.MinimumTemperature=list_cls("TemperatureType")
        self.MaximumTemperature=list_cls("TemperatureType")
        self.FloorSpaceMeasurementDimension=list_cls("DimensionType")
        self.PalletSpaceMeasurementDimension=list_cls("DimensionType")
        self.ShipmentDocumentReference=list_cls("DocumentReferenceType")
        self.CustomsDeclaration=list_cls("CustomsDeclarationType")
        
        
class TransportMeansType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.JourneyID=cbc()
        self.RegistrationNationalityID=cbc()
        self.RegistrationNationality=cbc()
        self.DirectionCode=cbc()
        self.TransportMeansTypeCode=cbc()
        self.TradeServiceCode=cbc()
        self.Stowage=list_cls("StowageType")
        self.AirTransport=list_cls("AirTransportType")
        self.RoadTransport=list_cls("RoadTransportType")
        self.RailTransport=list_cls("RailTransportType")
        self.MaritimeTransport=list_cls("MaritimeTransportType")
        self.OwnerParty=list_cls("PartyType")
        self.MeasurementDimension=list_cls("DimensionType")
        
        
class TransportScheduleType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.SequenceNumeric=cbc()
        self.ReferenceDate=cbc()
        self.ReferenceTime=cbc()
        self.ReliabilityPercent=cbc()
        self.Remarks=cbc()
        self.StatusLocation=list_cls("LocationType")
        self.ActualArrivalTransportEvent=list_cls("TransportEventType")
        self.ActualDepartureTransportEvent=list_cls("TransportEventType")
        self.EstimatedDepartureTransportEvent=list_cls("TransportEventType")
        self.EstimatedArrivalTransportEvent=list_cls("TransportEventType")
        self.PlannedDepartureTransportEvent=list_cls("TransportEventType")
        self.PlannedArrivalTransportEvent=list_cls("TransportEventType")
        
        
class TransportationSegmentType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.SequenceNumeric=cbc()
        self.TransportExecutionPlanReferenceID=cbc()
        self.TransportationService=list_cls("TransportationServiceType")
        self.TransportServiceProviderParty=list_cls("PartyType")
        self.ReferencedConsignment=list_cls("ConsignmentType")
        self.ShipmentStage=list_cls("ShipmentStageType")
        
        
class TransportationServiceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.TransportServiceCode=cbc()
        self.TariffClassCode=cbc()
        self.Priority=cbc()
        self.FreightRateClassCode=cbc()
        self.TransportationServiceDescription=cbc()
        self.TransportationServiceDetailsURI=cbc()
        self.NominationDate=cbc()
        self.NominationTime=cbc()
        self.Name=cbc()
        self.SequenceNumeric=cbc()
        self.TransportEquipment=list_cls("TransportEquipmentType")
        self.SupportedTransportEquipment=list_cls("TransportEquipmentType")
        self.UnsupportedTransportEquipment=list_cls("TransportEquipmentType")
        self.CommodityClassification=list_cls("CommodityClassificationType")
        self.SupportedCommodityClassification=list_cls("CommodityClassificationType")
        self.UnsupportedCommodityClassification=list_cls("CommodityClassificationType")
        self.TotalCapacityDimension=list_cls("DimensionType")
        self.ShipmentStage=list_cls("ShipmentStageType")
        self.TransportEvent=list_cls("TransportEventType")
        self.ResponsibleTransportServiceProviderParty=list_cls("PartyType")
        self.EnvironmentalEmission=list_cls("EnvironmentalEmissionType")
        self.EstimatedDurationPeriod=list_cls("PeriodType")
        self.ScheduledServiceFrequency=list_cls("ServiceFrequencyType")
        
        
class UnstructuredPriceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.PriceAmount=cbc()
        self.TimeAmount=cbc()
        
        
class UtilityItemType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.SubscriberID=cbc()
        self.SubscriberType=cbc()
        self.SubscriberTypeCode=cbc()
        self.Description=cbc()
        self.PackQuantity=cbc()
        self.PackSizeNumeric=cbc()
        self.ConsumptionType=cbc()
        self.ConsumptionTypeCode=cbc()
        self.CurrentChargeType=cbc()
        self.CurrentChargeTypeCode=cbc()
        self.OneTimeChargeType=cbc()
        self.OneTimeChargeTypeCode=cbc()
        self.TaxCategory=list_cls("TaxCategoryType")
        self.Contract=list_cls("ContractType")
        
        
class WebSiteAccessType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.URI=cbc()
        self.Password=cbc()
        self.Login=cbc()
        
        
class WinningPartyType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.Rank=cbc()
        self.Party=list_cls("PartyType")
        
        
class WorkPhaseReferenceType(cac):		
    def __init__(self):		
        cac.__init__(self)	
        self.ID=cbc()
        self.WorkPhaseCode=cbc()
        self.WorkPhase=cbc()
        self.ProgressPercent=cbc()
        self.StartDate=cbc()
        self.EndDate=cbc()
        self.WorkOrderDocumentReference=list_cls("DocumentReferenceType")


