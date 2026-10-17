import type { OcrResult } from '@/lib/receipt-parser'

/**
 * The real output of ML Kit on the Galaxy A55 for a photo of a supermarket cupom fiscal (NFC-e).
 * Tax ids, phone, address and access key are masked; the items and totals are as read, typos and all.
 * `top` is the recognizer's own: label ("Valor Total R$") and value ("59,39") come as separate lines
 * on the same printed row, and the header's mirror-image noise at the very top is part of the capture.
 * This capture predates the plugin returning `left`, so there is none.
 */
export const REAL_NFCE: OcrResult = {
  text: '',
  lines: [
    { text: '62428', top: 0.0324 },
    { text: 'O', top: 0.0444 },
    { text: 'EM', top: 0.048 },
    { text: 'no eo', top: 0.0483 },
    { text: 'Hd- 0quoog- ovodueg p - 02/ Aopng eny', top: 0.0564 },
    { text: 'PJK FRANCO E CIA LTDA', top: 0.2784 },
    { text: 'PAULO CESAR 3 CNPJ:00.000.000/0000-00 IE:0000000000', top: 0.2946 },
    { text: 'Telefone:(00)0000-0000', top: 0.324 },
    { text: 'RUA EXEMPLO. 000, BAIRRO. CIDADE PR. CEP:00000 000', top: 0.3436 },
    { text: 'DOCUMENTO AUXILIAR DA NOTA', top: 0.365 },
    { text: 'FISCAL DE CONSUMIDOR ELETRÔNICA', top: 0.3902 },
    { text: 'SEQ I CODJIGO JESCRICAO QTD UN VL UN VL TOTAL', top: 0.4191 },
    { text: '001 10131 BATATA MONALISA KG 1.610 KG X 4,49', top: 0.4495 },
    { text: '7,23', top: 0.4495 },
    { text: '002 12660 ANENDOTH CALDO BOM 400 1 UN X 6.99', top: 0.4765 },
    { text: '6,99', top: 0.4765 },
    { text: '6,99', top: 0.5027 },
    { text: '003 12660 AHENDOIM CALDO BOM 400 1 UN X 6,99', top: 0.5047 },
    { text: '004 10088 QJ MUSSARELA PDC KG 0.288 KG X 45,99', top: 0.5257 },
    { text: '13,25', top: 0.5257 },
    { text: 'X', top: 0.5272 },
    { text: '005 10134 PEPINO JAPONES KG 0.520 KG X 8,99', top: 0.5505 },
    { text: '4,67', top: 0.5547 },
    { text: '2.99', top: 0.575 },
    { text: '006 10155 LARAN JA PERA KG 0.970 KG', top: 0.576 },
    { text: '2,90', top: 0.5789 },
    { text: '007 10127 BANANA CATURRA KG 0.880 KG X 3,49', top: 0.6017 },
    { text: '3,07', top: 0.6032 },
    { text: '008 10144 CENOURA KG 0.675 KG X 5,49', top: 0.6243 },
    { text: '3,71', top: 0.6267 },
    { text: '009 39916 REFR H20 LIMONETO 500M 1 UN X 5.29', top: 0.6488 },
    { text: '5.29', top: 0.6512 },
    { text: '010 39916 REER H20 LIMONETO 500M 1 UN X 5,29', top: 0.6718 },
    { text: '5.29', top: 0.6748 },
    { text: '10', top: 0.701 },
    { text: 'Qtde. Total de Itens', top: 0.7029 },
    { text: '59,39', top: 0.7235 },
    { text: 'Valor Total R$', top: 0.7245 },
    { text: '59,39', top: 0.7556 },
    { text: 'Cartao de Debito', top: 0.7586 },
    { text: '59,39', top: 0.7828 },
    { text: 'Valor Recebido R$', top: 0.787 },
    { text: '0.00', top: 0.8115 },
    { text: 'Valor Troco R$', top: 0.8142 },
    { text: 'Consulte pela ChaVe de Acesso en', top: 0.8417 },
    { text: 'http://uww.fazende.pr.gov.br', top: 0.8691 },
    { text: '0000 0000 0000 0000 0000 0000 0000 0000 0000 0000', top: 0.8887 },
    { text: 'c CONSUHTDGR Nan ThEN FTrAnn', top: 0.9172 },
  ],
}

/**
 * The same kind of receipt, photographed again at the camera's full resolution (the first capture was the
 * already-shrunk upload), with the plugin's `left`. Two things this one shows: the text is much cleaner at
 * full size, and the photo is slightly tilted, so a value on the right of a row sits about 0.01 *lower* than
 * its label on the left. That is more than the height of a printed character and defeats matching by
 * "same top". Tax ids, phone, address and access key are masked.
 */
export const REAL_NFCE_TILTED: OcrResult = {
  text: '',
  lines: [
    { text: 'PJK FRANCO E CIA LTDA', top: 0.1904, left: 0.380 },
    { text: 'PRULO CESAR 3 CNPJ: 00.000.000/0000-00 IE:0000000000', top: 0.2078, left: 0.181 },
    { text: 'Telefone: (00) 0000-0000', top: 0.2341, left: 0.360 },
    { text: 'RUA EXEMPLO, 000. BAIRRO, CIDADE PR. CEP:00000000', top: 0.2547, left: 0.144 },
    { text: 'DOCUMENTO AUXILTAR DA NOTA', top: 0.2743, left: 0.290 },
    { text: 'FISCAL DE CONSUMIDOR ELETRÃ–NICA', top: 0.3027, left: 0.190 },
    { text: 'SEQ 1 CODIGO | JESCRIÃ‡AO QTD i UN I VL UN L TOTAL', top: 0.3355, left: 0.099 },
    { text: '001 10131 BATATA MONAL ISA KG 1.610 KG X 4.49', top: 0.3640, left: 0.093 },
    { text: '7,23', top: 0.3713, left: 0.797 },
    { text: '002 12660 AMENDOIM CALDO BOM 400 1 UN X 6.99', top: 0.3912, left: 0.093 },
    { text: '6,99', top: 0.3985, left: 0.795 },
    { text: '003 12660 AMENDOIM CALDO BOM 400 1 UN X 6.99', top: 0.4186, left: 0.094 },
    { text: '6,99', top: 0.4267, left: 0.790 },
    { text: '004 10088 QJ MUSSARELA PDC KG 0.288 KG X 45,99', top: 0.4458, left: 0.097 },
    { text: '13,25', top: 0.4520, left: 0.776 },
    { text: '005 10134 PEPINO JAPONES KG 0.520 KG X 8,99', top: 0.4703, left: 0.100 },
    { text: '4,67', top: 0.4772, left: 0.783 },
    { text: '006 10155 LARAN JA PERA KG 0.970 KG 2,99', top: 0.4966, left: 0.101 },
    { text: '2,90', top: 0.5032, left: 0.780 },
    { text: '007 10127 BANANA CATURRA KG 0.880 KG X 3,49', top: 0.5228, left: 0.102 },
    { text: '3,07', top: 0.5292, left: 0.778 },
    { text: '008 10144 CENOURA KG 0.675 KG X 5,49', top: 0.5466, left: 0.106 },
    { text: '3,71', top: 0.5525, left: 0.777 },
    { text: '009 39916 REFR H20 LIMONETO 500M 1 UN X 5.29', top: 0.5718, left: 0.105 },
    { text: '5.29', top: 0.5789, left: 0.776 },
    { text: '010 39916 REFR H20 LIMONETO 500M 1 UNX5,29', top: 0.5934, left: 0.112 },
    { text: '5.29', top: 0.6051, left: 0.772 },
    { text: 'Otde. Total de Itens', top: 0.6218, left: 0.093 },
    { text: '10', top: 0.6316, left: 0.806 },
    { text: 'Valor Total R$', top: 0.6431, left: 0.089 },
    { text: '59,39', top: 0.6532, left: 0.745 },
    { text: 'Cartao de Debito', top: 0.6757, left: 0.084 },
    { text: '59,39', top: 0.6846, left: 0.769 },
    { text: 'Valor Recebido R$', top: 0.7037, left: 0.079 },
    { text: '59,39', top: 0.7127, left: 0.772 },
    { text: 'Ualor Troco R$', top: 0.7314, left: 0.074 },
    { text: '0,00', top: 0.7412, left: 0.789 },
    { text: 'Consulte pela Chave de Acesso en', top: 0.7615, left: 0.295 },
    { text: 'http://uuu.fazenda .pr.guv.br', top: 0.7900, left: 0.327 },
    { text: '0000 0000 0000 0000 0000 0000 0000 0000 0000 0000', top: 0.8176, left: 0.134 },
    { text: 'DEO CONSUHIDOR NÃ£O IDEN IFICADO', top: 0.8495, left: 0.058 },
    { text: 'NÃºnero 178458 SÃ©rie 103 EnissÃ£o 01/08/26', top: 0.8743, left: 0.273 },
  ],
}
