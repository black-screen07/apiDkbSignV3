import java.io.*;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/**
 * ============================================================================
 * DKB Sign API - Client Java pour /v3/sign-upload-multiple
 * ============================================================================
 * 
 * Ce client permet de signer un ou plusieurs documents PDF avec des signataires
 * externes via l'API publique DKB Sign.
 * 
 * Prérequis : Java 11+ (utilise java.net.http.HttpClient)
 * 
 * Authentification : Header "X-API-Key" ou "Authorization: Bearer <api_key>"
 * 
 * ============================================================================
 * PARAMÈTRES SUPPORTÉS PAR L'API :
 * ============================================================================
 * 
 * [Form-Data Fields]
 * 
 * 1. documents[]           (fichiers PDF, OBLIGATOIRE)
 *    - Un ou plusieurs fichiers PDF à signer
 *    - Limite : 100 documents maximum par requête
 * 
 * 2. signers_data           (JSON string, OBLIGATOIRE)
 *    - Liste des signataires externes au format JSON
 *    - Champs par signataire :
 *      - name              (string, OBLIGATOIRE) : Nom du signataire
 *      - firstname         (string, OBLIGATOIRE) : Prénom du signataire
 *      - function          (string, OBLIGATOIRE) : Fonction/poste du signataire
 *      - email             (string, optionnel)   : Email du signataire
 *      - phone             (string, optionnel)   : Téléphone du signataire
 *      - signature_image   (string, optionnel)   : Nom du fichier image de signature
 *      - use_stored_signature (boolean, optionnel) : Si true, utilise la signature
 *                            stockée sur le serveur (associée à l'email du signataire)
 * 
 * 3. signature_params       (JSON string, OBLIGATOIRE)
 *    - Liste des paramètres de signature pour chaque document/signataire
 *    - Champs par entrée :
 *      - document_index    (int, OBLIGATOIRE)    : Index du document (0-based)
 *      - signer_index      (int, OBLIGATOIRE)    : Index du signataire dans signers_data (0-based)
 *      - pages             (array, OBLIGATOIRE)  : Positions de signature par page
 *          - page          (int)                 : Numéro de page (0-based)
 *          - signatures    (array)               : Liste de positions {x, y} en millimètres
 *      - show_signer_info  (boolean, optionnel)  : Affiche "Digital signed by DKBSIGN" + infos signataire sous la signature
 *      - sign_on_last_page (boolean, optionnel)  : Place la signature sur la dernière page automatiquement
 *      - custom_x          (int, optionnel)      : Position X personnalisée si sign_on_last_page=true (en mm)
 *      - signature_size    (object, optionnel)   : Dimensions personnalisées de l'image de signature
 *          - width         (int)                 : Largeur en pixels
 *          - height        (int)                 : Hauteur en pixels
 *      - signature_date    (object/string, optionnel) : Date de signature personnalisée
 *          - Format objet : {day, month, year, hour?, minute?, second?}
 *          - Format string : "DD/MM/YYYY à HH:MM:SS"
 *      - stamp_pages       (array of int, optionnel) : Pages sur lesquelles appliquer le cachet de l'utilisateur
 *      - qrcodes           (array, optionnel)    : QR codes à ajouter au document
 *          - page          (int)                 : Numéro de page (0-based)
 *          - x             (int)                 : Position X en mm
 *          - y             (int)                 : Position Y en mm
 *          - size          (int, défaut: 30)     : Taille du QR code en mm
 *          - data          (string, optionnel)   : Données du QR code (défaut: URL du PDF signé)
 *          - fill_color    (string, défaut: "blue")  : Couleur du QR code
 *          - back_color    (string, défaut: "white") : Couleur de fond du QR code
 *          - logo_path     (string, optionnel)   : URL ou chemin vers un logo à insérer au centre du QR
 *          - box_size      (int, défaut: 10)     : Taille des modules du QR code
 *          - border        (int, défaut: 4)      : Taille de la bordure du QR code
 * 
 * 4. signature_image_{i}    (fichier image, optionnel)
 *    - Image de signature pour le signataire à l'index {i}
 *    - Formats supportés : PNG (recommandé, avec transparence), JPEG, GIF, BMP
 *    - Si non fourni et use_stored_signature=false, l'image par défaut de l'utilisateur API est utilisée
 * 
 * ============================================================================
 * RÉPONSE DE L'API (200 OK) :
 * ============================================================================
 * {
 *   "message": "2 document(s) signé(s) avec succès avec signataires externes.",
 *   "signed_documents": [
 *     {
 *       "document_name": "contrat.pdf",
 *       "signed_pdf_url": "https://api.dkbsign.com/documents/signed/xxx.pdf",
 *       "signers": [{"name": "Dupont", "firstname": "Jean", "function": "Directeur"}]
 *     }
 *   ],
 *   "total_signatures": 2
 * }
 * ============================================================================
 */
public class DkbSignApiClient {

    // ========================================================================
    // CONFIGURATION - À MODIFIER SELON VOTRE ENVIRONNEMENT
    // ========================================================================
    private static final String API_BASE_URL = "https://votre-serveur-dkbsign.com";
    private static final String API_KEY = "VOTRE_CLE_API_ICI";
    private static final String SIGN_UPLOAD_MULTIPLE_ENDPOINT = "/v3/sign-upload-multiple";

    private final HttpClient httpClient;
    private final String apiBaseUrl;
    private final String apiKey;

    /**
     * Constructeur avec configuration personnalisée.
     */
    public DkbSignApiClient(String apiBaseUrl, String apiKey) {
        this.apiBaseUrl = apiBaseUrl;
        this.apiKey = apiKey;
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .build();
    }

    /**
     * Constructeur avec configuration par défaut.
     */
    public DkbSignApiClient() {
        this(API_BASE_URL, API_KEY);
    }

    // ========================================================================
    // CLASSES MODÈLES
    // ========================================================================

    /**
     * Représente un signataire externe.
     */
    public static class SignerData {
        private String name;                    // OBLIGATOIRE - Nom du signataire
        private String firstname;               // OBLIGATOIRE - Prénom du signataire
        private String function;                // OBLIGATOIRE - Fonction/poste
        private String email;                   // Optionnel - Email
        private String phone;                   // Optionnel - Téléphone
        private String signatureImage;          // Optionnel - Nom du fichier image de signature
        private Boolean useStoredSignature;     // Optionnel - Utiliser la signature stockée sur le serveur

        public SignerData(String name, String firstname, String function) {
            this.name = name;
            this.firstname = firstname;
            this.function = function;
        }

        public SignerData setEmail(String email) { this.email = email; return this; }
        public SignerData setPhone(String phone) { this.phone = phone; return this; }
        public SignerData setSignatureImage(String signatureImage) { this.signatureImage = signatureImage; return this; }
        public SignerData setUseStoredSignature(Boolean useStoredSignature) { this.useStoredSignature = useStoredSignature; return this; }

        public String toJson() {
            StringBuilder sb = new StringBuilder("{");
            sb.append("\"name\":\"").append(escapeJson(name)).append("\"");
            sb.append(",\"firstname\":\"").append(escapeJson(firstname)).append("\"");
            sb.append(",\"function\":\"").append(escapeJson(function)).append("\"");
            if (email != null) sb.append(",\"email\":\"").append(escapeJson(email)).append("\"");
            if (phone != null) sb.append(",\"phone\":\"").append(escapeJson(phone)).append("\"");
            if (signatureImage != null) sb.append(",\"signature_image\":\"").append(escapeJson(signatureImage)).append("\"");
            if (useStoredSignature != null) sb.append(",\"use_stored_signature\":").append(useStoredSignature);
            sb.append("}");
            return sb.toString();
        }
    }

    /**
     * Représente une position de signature sur une page.
     */
    public static class SignaturePosition {
        private int x; // Position X en millimètres
        private int y; // Position Y en millimètres

        public SignaturePosition(int x, int y) {
            this.x = x;
            this.y = y;
        }

        public String toJson() {
            return "{\"x\":" + x + ",\"y\":" + y + "}";
        }
    }

    /**
     * Représente les signatures à appliquer sur une page spécifique.
     */
    public static class PageSignatures {
        private int page;                               // Numéro de page (0-based)
        private List<SignaturePosition> signatures;     // Positions de signature

        public PageSignatures(int page, List<SignaturePosition> signatures) {
            this.page = page;
            this.signatures = signatures;
        }

        public String toJson() {
            StringBuilder sb = new StringBuilder("{\"page\":").append(page);
            sb.append(",\"signatures\":[");
            for (int i = 0; i < signatures.size(); i++) {
                if (i > 0) sb.append(",");
                sb.append(signatures.get(i).toJson());
            }
            sb.append("]}");
            return sb.toString();
        }
    }

    /**
     * Représente un QR code à ajouter au document.
     */
    public static class QrCodeParams {
        private int page;                   // Numéro de page (0-based)
        private int x;                      // Position X en mm
        private int y;                      // Position Y en mm
        private Integer size;               // Taille en mm (défaut: 30)
        private String data;                // Données du QR (défaut: URL du PDF signé)
        private String fillColor;           // Couleur du QR (défaut: "blue")
        private String backColor;           // Couleur de fond (défaut: "white")
        private String logoPath;            // URL/chemin vers un logo central
        private Integer boxSize;            // Taille des modules (défaut: 10)
        private Integer border;             // Taille bordure (défaut: 4)

        public QrCodeParams(int page, int x, int y) {
            this.page = page;
            this.x = x;
            this.y = y;
        }

        public QrCodeParams setSize(int size) { this.size = size; return this; }
        public QrCodeParams setData(String data) { this.data = data; return this; }
        public QrCodeParams setFillColor(String fillColor) { this.fillColor = fillColor; return this; }
        public QrCodeParams setBackColor(String backColor) { this.backColor = backColor; return this; }
        public QrCodeParams setLogoPath(String logoPath) { this.logoPath = logoPath; return this; }
        public QrCodeParams setBoxSize(int boxSize) { this.boxSize = boxSize; return this; }
        public QrCodeParams setBorder(int border) { this.border = border; return this; }

        public String toJson() {
            StringBuilder sb = new StringBuilder("{");
            sb.append("\"page\":").append(page);
            sb.append(",\"x\":").append(x);
            sb.append(",\"y\":").append(y);
            if (size != null) sb.append(",\"size\":").append(size);
            if (data != null) sb.append(",\"data\":\"").append(escapeJson(data)).append("\"");
            if (fillColor != null) sb.append(",\"fill_color\":\"").append(escapeJson(fillColor)).append("\"");
            if (backColor != null) sb.append(",\"back_color\":\"").append(escapeJson(backColor)).append("\"");
            if (logoPath != null) sb.append(",\"logo_path\":\"").append(escapeJson(logoPath)).append("\"");
            if (boxSize != null) sb.append(",\"box_size\":").append(boxSize);
            if (border != null) sb.append(",\"border\":").append(border);
            sb.append("}");
            return sb.toString();
        }
    }

    /**
     * Représente une date de signature personnalisée.
     */
    public static class SignatureDate {
        private int day;
        private int month;
        private int year;
        private Integer hour;       // Optionnel (défaut: 0)
        private Integer minute;     // Optionnel (défaut: 0)
        private Integer second;     // Optionnel (défaut: 0)

        public SignatureDate(int day, int month, int year) {
            this.day = day;
            this.month = month;
            this.year = year;
        }

        public SignatureDate setTime(int hour, int minute, int second) {
            this.hour = hour;
            this.minute = minute;
            this.second = second;
            return this;
        }

        public String toJson() {
            StringBuilder sb = new StringBuilder("{");
            sb.append("\"day\":").append(day);
            sb.append(",\"month\":").append(month);
            sb.append(",\"year\":").append(year);
            if (hour != null) sb.append(",\"hour\":").append(hour);
            if (minute != null) sb.append(",\"minute\":").append(minute);
            if (second != null) sb.append(",\"second\":").append(second);
            sb.append("}");
            return sb.toString();
        }
    }

    /**
     * Représente la taille personnalisée d'une image de signature.
     */
    public static class SignatureSize {
        private int width;  // Largeur en pixels
        private int height; // Hauteur en pixels

        public SignatureSize(int width, int height) {
            this.width = width;
            this.height = height;
        }

        public String toJson() {
            return "{\"width\":" + width + ",\"height\":" + height + "}";
        }
    }

    /**
     * Paramètres de signature pour un document/signataire spécifique.
     */
    public static class SignatureParam {
        private int documentIndex;                      // OBLIGATOIRE - Index du document (0-based)
        private int signerIndex;                        // OBLIGATOIRE - Index du signataire (0-based)
        private List<PageSignatures> pages;             // OBLIGATOIRE - Positions de signature par page
        private Boolean showSignerInfo;                 // Optionnel - Afficher les infos du signataire sous la signature
        private Boolean signOnLastPage;                 // Optionnel - Signer sur la dernière page automatiquement
        private Integer customX;                        // Optionnel - Position X si signOnLastPage=true (en mm)
        private SignatureSize signatureSize;             // Optionnel - Taille personnalisée de l'image
        private SignatureDate signatureDate;             // Optionnel - Date de signature personnalisée
        private String signatureDateString;              // Optionnel - Date au format string "DD/MM/YYYY à HH:MM:SS"
        private List<Integer> stampPages;                // Optionnel - Pages pour le cachet
        private List<QrCodeParams> qrcodes;             // Optionnel - QR codes à ajouter

        public SignatureParam(int documentIndex, int signerIndex, List<PageSignatures> pages) {
            this.documentIndex = documentIndex;
            this.signerIndex = signerIndex;
            this.pages = pages;
        }

        public SignatureParam setShowSignerInfo(boolean showSignerInfo) { this.showSignerInfo = showSignerInfo; return this; }
        public SignatureParam setSignOnLastPage(boolean signOnLastPage) { this.signOnLastPage = signOnLastPage; return this; }
        public SignatureParam setCustomX(int customX) { this.customX = customX; return this; }
        public SignatureParam setSignatureSize(SignatureSize signatureSize) { this.signatureSize = signatureSize; return this; }
        public SignatureParam setSignatureDate(SignatureDate signatureDate) { this.signatureDate = signatureDate; return this; }
        public SignatureParam setSignatureDateString(String signatureDateString) { this.signatureDateString = signatureDateString; return this; }
        public SignatureParam setStampPages(List<Integer> stampPages) { this.stampPages = stampPages; return this; }
        public SignatureParam setQrcodes(List<QrCodeParams> qrcodes) { this.qrcodes = qrcodes; return this; }

        public String toJson() {
            StringBuilder sb = new StringBuilder("{");
            sb.append("\"document_index\":").append(documentIndex);
            sb.append(",\"signer_index\":").append(signerIndex);

            // Pages
            sb.append(",\"pages\":[");
            for (int i = 0; i < pages.size(); i++) {
                if (i > 0) sb.append(",");
                sb.append(pages.get(i).toJson());
            }
            sb.append("]");

            if (showSignerInfo != null) sb.append(",\"show_signer_info\":").append(showSignerInfo);
            if (signOnLastPage != null) sb.append(",\"sign_on_last_page\":").append(signOnLastPage);
            if (customX != null) sb.append(",\"custom_x\":").append(customX);
            if (signatureSize != null) sb.append(",\"signature_size\":").append(signatureSize.toJson());

            // Date de signature
            if (signatureDate != null) {
                sb.append(",\"signature_date\":").append(signatureDate.toJson());
            } else if (signatureDateString != null) {
                sb.append(",\"signature_date\":\"").append(escapeJson(signatureDateString)).append("\"");
            }

            // Stamp pages
            if (stampPages != null && !stampPages.isEmpty()) {
                sb.append(",\"stamp_pages\":[");
                for (int i = 0; i < stampPages.size(); i++) {
                    if (i > 0) sb.append(",");
                    sb.append(stampPages.get(i));
                }
                sb.append("]");
            }

            // QR codes
            if (qrcodes != null && !qrcodes.isEmpty()) {
                sb.append(",\"qrcodes\":[");
                for (int i = 0; i < qrcodes.size(); i++) {
                    if (i > 0) sb.append(",");
                    sb.append(qrcodes.get(i).toJson());
                }
                sb.append("]");
            }

            sb.append("}");
            return sb.toString();
        }
    }

    /**
     * Résultat de la signature d'un document.
     */
    public static class SignResult {
        public final int statusCode;
        public final String responseBody;
        public final boolean success;

        public SignResult(int statusCode, String responseBody) {
            this.statusCode = statusCode;
            this.responseBody = responseBody;
            this.success = (statusCode == 200);
        }

        @Override
        public String toString() {
            return "SignResult{statusCode=" + statusCode + ", success=" + success + ", body=" + responseBody + "}";
        }
    }

    // ========================================================================
    // MÉTHODE PRINCIPALE - SIGNATURE DE DOCUMENTS
    // ========================================================================

    /**
     * Signe un ou plusieurs documents PDF avec des signataires externes.
     *
     * @param documentPaths     Liste des chemins vers les fichiers PDF à signer
     * @param signersData       Liste des signataires externes
     * @param signatureParams   Liste des paramètres de signature
     * @param signatureImages   Map (index signataire -> chemin image), peut être null
     * @return SignResult avec le code HTTP et le corps de la réponse
     * @throws IOException          En cas d'erreur de lecture de fichier
     * @throws InterruptedException En cas d'interruption de la requête HTTP
     */
    public SignResult signUploadMultiple(
            List<Path> documentPaths,
            List<SignerData> signersData,
            List<SignatureParam> signatureParams,
            Map<Integer, Path> signatureImages
    ) throws IOException, InterruptedException {

        // Générer un boundary unique pour le multipart
        String boundary = "----DkbSign" + UUID.randomUUID().toString().replace("-", "");

        // Construire le corps multipart
        byte[] body = buildMultipartBody(boundary, documentPaths, signersData, signatureParams, signatureImages);

        // Construire la requête HTTP
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(apiBaseUrl + SIGN_UPLOAD_MULTIPLE_ENDPOINT))
                .header("X-API-Key", apiKey)
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        // Envoyer la requête
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        return new SignResult(response.statusCode(), response.body());
    }

    // ========================================================================
    // CONSTRUCTION DU CORPS MULTIPART
    // ========================================================================

    private byte[] buildMultipartBody(
            String boundary,
            List<Path> documentPaths,
            List<SignerData> signersData,
            List<SignatureParam> signatureParams,
            Map<Integer, Path> signatureImages
    ) throws IOException {

        ByteArrayOutputStream baos = new ByteArrayOutputStream();

        // 1. Ajouter les documents PDF (champ "documents")
        for (Path docPath : documentPaths) {
            writeFilePart(baos, boundary, "documents", docPath, "application/pdf");
        }

        // 2. Ajouter signers_data (JSON string)
        String signersDataJson = "[";
        for (int i = 0; i < signersData.size(); i++) {
            if (i > 0) signersDataJson += ",";
            signersDataJson += signersData.get(i).toJson();
        }
        signersDataJson += "]";
        writeTextPart(baos, boundary, "signers_data", signersDataJson);

        // 3. Ajouter signature_params (JSON string)
        String signatureParamsJson = "[";
        for (int i = 0; i < signatureParams.size(); i++) {
            if (i > 0) signatureParamsJson += ",";
            signatureParamsJson += signatureParams.get(i).toJson();
        }
        signatureParamsJson += "]";
        writeTextPart(baos, boundary, "signature_params", signatureParamsJson);

        // 4. Ajouter les images de signature (signature_image_0, signature_image_1, etc.)
        if (signatureImages != null) {
            for (Map.Entry<Integer, Path> entry : signatureImages.entrySet()) {
                String fieldName = "signature_image_" + entry.getKey();
                String mimeType = detectMimeType(entry.getValue());
                writeFilePart(baos, boundary, fieldName, entry.getValue(), mimeType);
            }
        }

        // Terminer le multipart
        baos.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));

        return baos.toByteArray();
    }

    private void writeTextPart(ByteArrayOutputStream baos, String boundary, String fieldName, String value) throws IOException {
        String part = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + fieldName + "\"\r\n"
                + "Content-Type: text/plain; charset=UTF-8\r\n"
                + "\r\n"
                + value + "\r\n";
        baos.write(part.getBytes(StandardCharsets.UTF_8));
    }

    private void writeFilePart(ByteArrayOutputStream baos, String boundary, String fieldName, Path filePath, String mimeType) throws IOException {
        String header = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + fieldName + "\"; filename=\"" + filePath.getFileName() + "\"\r\n"
                + "Content-Type: " + mimeType + "\r\n"
                + "\r\n";
        baos.write(header.getBytes(StandardCharsets.UTF_8));
        baos.write(Files.readAllBytes(filePath));
        baos.write("\r\n".getBytes(StandardCharsets.UTF_8));
    }

    private String detectMimeType(Path filePath) {
        String fileName = filePath.getFileName().toString().toLowerCase();
        if (fileName.endsWith(".png")) return "image/png";
        if (fileName.endsWith(".jpg") || fileName.endsWith(".jpeg")) return "image/jpeg";
        if (fileName.endsWith(".gif")) return "image/gif";
        if (fileName.endsWith(".bmp")) return "image/bmp";
        return "application/octet-stream";
    }

    private static String escapeJson(String value) {
        if (value == null) return "";
        return value
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }

    // ========================================================================
    // EXEMPLES D'UTILISATION
    // ========================================================================

    public static void main(String[] args) {
        try {
            // ================================================================
            // EXEMPLE 1 : Signature simple - 1 document, 1 signataire
            // ================================================================
            System.out.println("=== EXEMPLE 1 : Signature simple ===\n");
            exempleSignatureSimple();

            // ================================================================
            // EXEMPLE 2 : Signature avancée - Tous les paramètres
            // ================================================================
            System.out.println("\n=== EXEMPLE 2 : Signature avancée (tous paramètres) ===\n");
            exempleSignatureAvancee();

            // ================================================================
            // EXEMPLE 3 : Multi-documents, multi-signataires
            // ================================================================
            System.out.println("\n=== EXEMPLE 3 : Multi-documents, multi-signataires ===\n");
            exempleMultiDocumentsMultiSignataires();

            // ================================================================
            // EXEMPLE 4 : Signature sur la dernière page
            // ================================================================
            System.out.println("\n=== EXEMPLE 4 : Signature sur la dernière page ===\n");
            exempleSignatureDernierePage();

            // ================================================================
            // EXEMPLE 5 : Utilisation de signatures stockées sur le serveur
            // ================================================================
            System.out.println("\n=== EXEMPLE 5 : Signatures stockées ===\n");
            exempleSignaturesStockees();

        } catch (Exception e) {
            System.err.println("Erreur : " + e.getMessage());
            e.printStackTrace();
        }
    }

    // -----------------------------------------------------------------------
    // EXEMPLE 1 : Signature simple
    // -----------------------------------------------------------------------
    private static void exempleSignatureSimple() throws IOException, InterruptedException {
        DkbSignApiClient client = new DkbSignApiClient(
                "https://votre-serveur-dkbsign.com",
                "votre-cle-api"
        );

        // Document à signer
        List<Path> documents = List.of(
                Path.of("/chemin/vers/contrat.pdf")
        );

        // Signataire
        List<SignerData> signers = List.of(
                new SignerData("Dupont", "Jean", "Directeur Général")
                        .setEmail("jean.dupont@entreprise.com")
        );

        // Paramètres : signature en bas à droite de la page 0
        List<SignatureParam> params = List.of(
                new SignatureParam(0, 0, List.of(
                        new PageSignatures(0, List.of(
                                new SignaturePosition(120, 240)
                        ))
                ))
        );

        // Image de signature du signataire 0
        Map<Integer, Path> images = Map.of(
                0, Path.of("/chemin/vers/signature_dupont.png")
        );

        SignResult result = client.signUploadMultiple(documents, signers, params, images);
        System.out.println("Status: " + result.statusCode);
        System.out.println("Réponse: " + result.responseBody);
    }

    // -----------------------------------------------------------------------
    // EXEMPLE 2 : Signature avancée avec TOUS les paramètres
    // -----------------------------------------------------------------------
    private static void exempleSignatureAvancee() throws IOException, InterruptedException {
        DkbSignApiClient client = new DkbSignApiClient(
                "https://votre-serveur-dkbsign.com",
                "votre-cle-api"
        );

        // Document
        List<Path> documents = List.of(
                Path.of("/chemin/vers/contrat_complet.pdf")
        );

        // Signataire avec tous les champs
        List<SignerData> signers = List.of(
                new SignerData("Martin", "Sophie", "Directrice Financière")
                        .setEmail("sophie.martin@entreprise.com")
                        .setPhone("+33612345678")
                        .setSignatureImage("signature_sophie.png")
        );

        // Paramètres avec TOUTES les options
        SignatureParam param = new SignatureParam(0, 0, List.of(
                // Signature sur la page 0
                new PageSignatures(0, List.of(
                        new SignaturePosition(100, 200)
                )),
                // Signature aussi sur la page 2
                new PageSignatures(2, List.of(
                        new SignaturePosition(120, 250)
                ))
        ));

        // Activer l'affichage des infos du signataire sous la signature
        param.setShowSignerInfo(true);

        // Taille personnalisée de l'image de signature (en pixels)
        param.setSignatureSize(new SignatureSize(200, 80));

        // Date de signature personnalisée (format objet)
        param.setSignatureDate(
                new SignatureDate(15, 3, 2025)
                        .setTime(14, 30, 45)
        );

        // Appliquer le cachet de l'utilisateur sur les pages 0 et 2
        param.setStampPages(List.of(0, 2));

        // Ajouter des QR codes
        param.setQrcodes(List.of(
                // QR code bleu sur la page 0
                new QrCodeParams(0, 10, 10)
                        .setSize(25)
                        .setData("https://verification.dkbsign.com/doc/12345")
                        .setFillColor("blue")
                        .setBackColor("white")
                        .setBoxSize(10)
                        .setBorder(4),
                // QR code noir avec logo sur la page 2
                new QrCodeParams(2, 160, 10)
                        .setSize(30)
                        .setData("https://verification.dkbsign.com/doc/12345")
                        .setFillColor("black")
                        .setLogoPath("https://exemple.com/logo.png")
        ));

        List<SignatureParam> params = List.of(param);

        // Image de signature
        Map<Integer, Path> images = Map.of(
                0, Path.of("/chemin/vers/signature_sophie.png")
        );

        SignResult result = client.signUploadMultiple(documents, signers, params, images);
        System.out.println("Status: " + result.statusCode);
        System.out.println("Réponse: " + result.responseBody);
    }

    // -----------------------------------------------------------------------
    // EXEMPLE 3 : Multi-documents, multi-signataires
    // -----------------------------------------------------------------------
    private static void exempleMultiDocumentsMultiSignataires() throws IOException, InterruptedException {
        DkbSignApiClient client = new DkbSignApiClient(
                "https://votre-serveur-dkbsign.com",
                "votre-cle-api"
        );

        // 3 documents à signer
        List<Path> documents = List.of(
                Path.of("/chemin/vers/contrat_travail.pdf"),
                Path.of("/chemin/vers/avenant.pdf"),
                Path.of("/chemin/vers/nda.pdf")
        );

        // 2 signataires
        List<SignerData> signers = List.of(
                new SignerData("Dupont", "Jean", "Directeur RH")
                        .setEmail("jean.dupont@entreprise.com"),
                new SignerData("Bernard", "Marie", "Employée")
                        .setEmail("marie.bernard@entreprise.com")
                        .setPhone("+33698765432")
        );

        // Paramètres : chaque signataire signe chaque document
        List<SignatureParam> params = new ArrayList<>();

        // Document 0 - Signataire 0 (Dupont) signe en haut
        params.add(new SignatureParam(0, 0, List.of(
                new PageSignatures(0, List.of(new SignaturePosition(20, 200)))
        )).setShowSignerInfo(true));

        // Document 0 - Signataire 1 (Bernard) signe en bas
        params.add(new SignatureParam(0, 1, List.of(
                new PageSignatures(0, List.of(new SignaturePosition(20, 100)))
        )).setShowSignerInfo(true));

        // Document 1 - Signataire 0 signe
        params.add(new SignatureParam(1, 0, List.of(
                new PageSignatures(0, List.of(new SignaturePosition(100, 200)))
        )));

        // Document 1 - Signataire 1 signe
        params.add(new SignatureParam(1, 1, List.of(
                new PageSignatures(0, List.of(new SignaturePosition(100, 100)))
        )));

        // Document 2 - Les deux signent avec date personnalisée (format string)
        params.add(new SignatureParam(2, 0, List.of(
                new PageSignatures(0, List.of(new SignaturePosition(30, 180)))
        )).setSignatureDateString("01/06/2025 à 09:00:00"));

        params.add(new SignatureParam(2, 1, List.of(
                new PageSignatures(0, List.of(new SignaturePosition(30, 80)))
        )).setSignatureDateString("01/06/2025 à 09:00:00"));

        // Images de signature pour chaque signataire
        Map<Integer, Path> images = new HashMap<>();
        images.put(0, Path.of("/chemin/vers/signature_dupont.png"));
        images.put(1, Path.of("/chemin/vers/signature_bernard.png"));

        SignResult result = client.signUploadMultiple(documents, signers, params, images);
        System.out.println("Status: " + result.statusCode);
        System.out.println("Réponse: " + result.responseBody);
    }

    // -----------------------------------------------------------------------
    // EXEMPLE 4 : Signature automatique sur la dernière page
    // -----------------------------------------------------------------------
    private static void exempleSignatureDernierePage() throws IOException, InterruptedException {
        DkbSignApiClient client = new DkbSignApiClient(
                "https://votre-serveur-dkbsign.com",
                "votre-cle-api"
        );

        List<Path> documents = List.of(
                Path.of("/chemin/vers/document_long.pdf")
        );

        List<SignerData> signers = List.of(
                new SignerData("Leroy", "Pierre", "Avocat")
                        .setEmail("pierre.leroy@cabinet.com")
        );

        // sign_on_last_page=true : la signature sera automatiquement placée
        // sur la dernière page du document, quelle que soit sa longueur.
        // Les positions dans "pages" servent de positions par défaut si fournies,
        // sinon l'API calcule automatiquement les positions.
        SignatureParam param = new SignatureParam(0, 0, List.of(
                new PageSignatures(0, List.of(
                        new SignaturePosition(120, 200)
                ))
        ));
        param.setSignOnLastPage(true);
        param.setCustomX(120);  // Position X personnalisée sur la dernière page
        param.setShowSignerInfo(true);

        // Ajouter un QR code de vérification sur la dernière page aussi
        param.setQrcodes(List.of(
                new QrCodeParams(0, 10, 270)
                        .setSize(20)
                        .setFillColor("darkblue")
        ));

        List<SignatureParam> params = List.of(param);

        Map<Integer, Path> images = Map.of(
                0, Path.of("/chemin/vers/signature_leroy.png")
        );

        SignResult result = client.signUploadMultiple(documents, signers, params, images);
        System.out.println("Status: " + result.statusCode);
        System.out.println("Réponse: " + result.responseBody);
    }

    // -----------------------------------------------------------------------
    // EXEMPLE 5 : Utilisation de signatures stockées sur le serveur
    // -----------------------------------------------------------------------
    private static void exempleSignaturesStockees() throws IOException, InterruptedException {
        DkbSignApiClient client = new DkbSignApiClient(
                "https://votre-serveur-dkbsign.com",
                "votre-cle-api"
        );

        List<Path> documents = List.of(
                Path.of("/chemin/vers/facture.pdf")
        );

        // Signataire avec use_stored_signature=true
        // L'API cherchera l'image de signature déjà enregistrée sur le serveur
        // pour l'email fourni (via la route /v3/external-signatures)
        List<SignerData> signers = List.of(
                new SignerData("Moreau", "Claire", "Comptable")
                        .setEmail("claire.moreau@entreprise.com")
                        .setUseStoredSignature(true)  // Pas besoin d'envoyer l'image !
        );

        List<SignatureParam> params = List.of(
                new SignatureParam(0, 0, List.of(
                        new PageSignatures(0, List.of(
                                new SignaturePosition(100, 200)
                        ))
                )).setShowSignerInfo(true)
        );

        // Pas d'images à envoyer car on utilise les signatures stockées
        SignResult result = client.signUploadMultiple(documents, signers, params, null);
        System.out.println("Status: " + result.statusCode);
        System.out.println("Réponse: " + result.responseBody);
    }
}
