package com.example.opentextsignature.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.*;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

/**
 * Service de signature électronique via l'API DKB Sign.
 * 
 * Utilisation simplifiée : envoie un fichier PDF et l'email du signataire,
 * récupère le PDF signé en retour.
 * 
 * Configuration dans application.properties :
 *   dkbsign.api.url=https://votre-serveur-dkbsign.com
 *   dkbsign.api.key=VOTRE_CLE_API
 *   dkbsign.signer.name=Dupont
 *   dkbsign.signer.firstname=Jean
 *   dkbsign.signer.function=Directeur
 *   dkbsign.signature.x=100
 *   dkbsign.signature.y=200
 *   dkbsign.signature.page=0
 */
@Service
public class SignatureProviderService {

    @Value("${dkbsign.api.url:https://votre-serveur-dkbsign.com}")
    private String apiUrl;

    @Value("${dkbsign.api.key:VOTRE_CLE_API}")
    private String apiKey;

    // Infos signataire par défaut (surchargées par les properties)
    @Value("${dkbsign.signer.name:Signataire}")
    private String signerName;

    @Value("${dkbsign.signer.firstname:Default}")
    private String signerFirstname;

    @Value("${dkbsign.signer.function:Responsable}")
    private String signerFunction;

    // Position de signature par défaut (en mm)
    @Value("${dkbsign.signature.x:100}")
    private int signatureX;

    @Value("${dkbsign.signature.y:200}")
    private int signatureY;

    @Value("${dkbsign.signature.page:0}")
    private int signaturePage;

    private final HttpClient httpClient = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .build();

    /**
     * Signe un fichier PDF via l'API DKB Sign.
     * 
     * Utilise la signature stockée sur le serveur pour l'email fourni
     * (use_stored_signature=true). Si aucune signature n'est stockée,
     * l'API utilisera l'image de signature par défaut de l'utilisateur API.
     *
     * @param file  Le fichier PDF à signer
     * @param email L'email du signataire (utilisé pour récupérer la signature stockée)
     * @return Le fichier PDF signé
     * @throws SignatureException En cas d'erreur lors de la signature
     */
    public File sign(File file, String email) {
        try {
            // 1. Construire la requête multipart
            String boundary = "----DkbSign" + UUID.randomUUID().toString().replace("-", "");
            byte[] body = buildRequestBody(boundary, file, email);

            // 2. Envoyer la requête à l'API
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(apiUrl + "/v3/sign-upload-multiple"))
                    .header("X-API-Key", apiKey)
                    .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            // 3. Vérifier la réponse
            if (response.statusCode() != 200) {
                throw new SignatureException(
                        "Erreur API DKB Sign (HTTP " + response.statusCode() + "): " + response.body()
                );
            }

            // 4. Extraire l'URL du PDF signé depuis la réponse JSON
            String signedPdfUrl = extractSignedPdfUrl(response.body());

            // 5. Télécharger le PDF signé
            return downloadSignedPdf(signedPdfUrl);

        } catch (SignatureException e) {
            throw e;
        } catch (Exception e) {
            throw new SignatureException("Erreur lors de la signature du document: " + e.getMessage(), e);
        }
    }

    /**
     * Variante avec flag explicite pour utiliser la signature stockée sur le serveur.
     * 
     * Si useStoredSignature=true, l'API cherche l'image de signature déjà enregistrée
     * sur le serveur pour l'email fourni (via la route /v3/external-signatures).
     * Si useStoredSignature=false et aucune image n'est fournie, l'API utilise
     * l'image par défaut de l'utilisateur API.
     *
     * @param file                Le fichier PDF à signer
     * @param email               L'email du signataire
     * @param useStoredSignature  Si true, utilise la signature stockée sur le serveur pour cet email
     * @return Le fichier PDF signé
     */
    public File sign(File file, String email, boolean useStoredSignature) {
        try {
            String boundary = "----DkbSign" + UUID.randomUUID().toString().replace("-", "");
            byte[] body = buildRequestBody(boundary, file, email, null, useStoredSignature);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(apiUrl + "/v3/sign-upload-multiple"))
                    .header("X-API-Key", apiKey)
                    .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() != 200) {
                throw new SignatureException(
                        "Erreur API DKB Sign (HTTP " + response.statusCode() + "): " + response.body()
                );
            }

            String signedPdfUrl = extractSignedPdfUrl(response.body());
            return downloadSignedPdf(signedPdfUrl);

        } catch (SignatureException e) {
            throw e;
        } catch (Exception e) {
            throw new SignatureException("Erreur lors de la signature du document: " + e.getMessage(), e);
        }
    }

    /**
     * Variante avec image de signature fournie en paramètre.
     * L'image envoyée sera utilisée à la place de toute signature stockée.
     *
     * @param file           Le fichier PDF à signer
     * @param email          L'email du signataire
     * @param signatureImage Le fichier image de la signature (PNG recommandé)
     * @return Le fichier PDF signé
     */
    public File sign(File file, String email, File signatureImage) {
        try {
            String boundary = "----DkbSign" + UUID.randomUUID().toString().replace("-", "");
            byte[] body = buildRequestBody(boundary, file, email, signatureImage, false);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(apiUrl + "/v3/sign-upload-multiple"))
                    .header("X-API-Key", apiKey)
                    .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() != 200) {
                throw new SignatureException(
                        "Erreur API DKB Sign (HTTP " + response.statusCode() + "): " + response.body()
                );
            }

            String signedPdfUrl = extractSignedPdfUrl(response.body());
            return downloadSignedPdf(signedPdfUrl);

        } catch (SignatureException e) {
            throw e;
        } catch (Exception e) {
            throw new SignatureException("Erreur lors de la signature du document: " + e.getMessage(), e);
        }
    }

    // ========================================================================
    // CONSTRUCTION DU CORPS DE LA REQUÊTE
    // ========================================================================

    /**
     * Construit le corps multipart avec signature stockée (use_stored_signature=true).
     */
    private byte[] buildRequestBody(String boundary, File pdfFile, String email) throws IOException {
        return buildRequestBody(boundary, pdfFile, email, null, true);
    }

    /**
     * Construit le corps multipart complet.
     *
     * @param boundary            Boundary du multipart
     * @param pdfFile             Fichier PDF à signer
     * @param email               Email du signataire
     * @param signatureImage      Image de signature (null si non fournie)
     * @param useStoredSignature  Si true, demande à l'API d'utiliser la signature stockée pour cet email
     */
    private byte[] buildRequestBody(String boundary, File pdfFile, String email, File signatureImage, boolean useStoredSignature) throws IOException {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();

        // 1. Document PDF
        writeFilePart(baos, boundary, "documents", pdfFile.toPath(), "application/pdf");

        // 2. signers_data - JSON simplifié avec un seul signataire
        String signersDataJson = "[{"
                + "\"name\":\"" + escapeJson(signerName) + "\""
                + ",\"firstname\":\"" + escapeJson(signerFirstname) + "\""
                + ",\"function\":\"" + escapeJson(signerFunction) + "\""
                + ",\"email\":\"" + escapeJson(email) + "\""
                + (useStoredSignature ? ",\"use_stored_signature\":true" : "")
                + "}]";
        writeTextPart(baos, boundary, "signers_data", signersDataJson);

        // 3. signature_params - Position simple sur une page
        String signatureParamsJson = "[{"
                + "\"document_index\":0"
                + ",\"signer_index\":0"
                + ",\"show_signer_info\":true"
                + ",\"pages\":[{"
                + "\"page\":" + signaturePage
                + ",\"signatures\":[{\"x\":" + signatureX + ",\"y\":" + signatureY + "}]"
                + "}]"
                + "}]";
        writeTextPart(baos, boundary, "signature_params", signatureParamsJson);

        // 4. Image de signature (si fournie)
        if (signatureImage != null) {
            String mimeType = detectMimeType(signatureImage.getName());
            writeFilePart(baos, boundary, "signature_image_0", signatureImage.toPath(), mimeType);
        }

        // Fin du multipart
        baos.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        return baos.toByteArray();
    }

    // ========================================================================
    // UTILITAIRES MULTIPART
    // ========================================================================

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

    // ========================================================================
    // EXTRACTION DE LA RÉPONSE ET TÉLÉCHARGEMENT
    // ========================================================================

    /**
     * Extrait l'URL du PDF signé depuis la réponse JSON de l'API.
     * Parse manuellement pour éviter une dépendance à Jackson/Gson.
     */
    private String extractSignedPdfUrl(String jsonResponse) {
        // Chercher "signed_pdf_url":"..."
        String key = "\"signed_pdf_url\":\"";
        int startIndex = jsonResponse.indexOf(key);
        if (startIndex == -1) {
            throw new SignatureException(
                    "URL du PDF signé introuvable dans la réponse: " + jsonResponse
            );
        }
        startIndex += key.length();
        int endIndex = jsonResponse.indexOf("\"", startIndex);
        if (endIndex == -1) {
            throw new SignatureException(
                    "Format de réponse inattendu: " + jsonResponse
            );
        }
        return jsonResponse.substring(startIndex, endIndex);
    }

    /**
     * Télécharge le PDF signé depuis l'URL retournée par l'API.
     */
    private File downloadSignedPdf(String signedPdfUrl) throws IOException, InterruptedException {
        HttpRequest downloadRequest = HttpRequest.newBuilder()
                .uri(URI.create(signedPdfUrl))
                .header("X-API-Key", apiKey)
                .GET()
                .build();

        // Créer un fichier temporaire pour stocker le PDF signé
        File signedFile = File.createTempFile("signed_", ".pdf");
        signedFile.deleteOnExit();

        HttpResponse<Path> downloadResponse = httpClient.send(
                downloadRequest,
                HttpResponse.BodyHandlers.ofFile(signedFile.toPath())
        );

        if (downloadResponse.statusCode() != 200) {
            throw new SignatureException(
                    "Erreur lors du téléchargement du PDF signé (HTTP " + downloadResponse.statusCode() + ")"
            );
        }

        return signedFile;
    }

    // ========================================================================
    // UTILITAIRES
    // ========================================================================

    private static String escapeJson(String value) {
        if (value == null) return "";
        return value
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }

    private static String detectMimeType(String fileName) {
        String lower = fileName.toLowerCase();
        if (lower.endsWith(".png")) return "image/png";
        if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
        if (lower.endsWith(".gif")) return "image/gif";
        if (lower.endsWith(".bmp")) return "image/bmp";
        return "application/octet-stream";
    }

    // ========================================================================
    // EXCEPTION PERSONNALISÉE
    // ========================================================================

    public static class SignatureException extends RuntimeException {
        public SignatureException(String message) {
            super(message);
        }

        public SignatureException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
