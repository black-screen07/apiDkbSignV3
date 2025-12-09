# Réponses aux questions sur l'API DKB Sign V3

## Accès et tests

**Pour obtenir une clé API :** Vous devez d'abord vous connecter normalement à DKB Sign, puis demander la génération d'une clé API via l'interface ou en contactant le support. Cette clé vous permettra d'utiliser l'API sans avoir à vous reconnecter à chaque fois.

**Pour faire des tests :** Nous mettons à disposition un serveur de test où vous pouvez essayer l'API sans risque. L'adresse est différente du serveur de production et vos tests n'affecteront pas les vrais documents.

## Questions sur les paramètres d'entrée

### Images de signature (signature_image_X)

**Dans quel cas utiliser les images de signature pour les signataires externes ?**
Utilisez cette fonction quand vous voulez faire signer des personnes qui ne sont pas enregistrées dans votre système DKB Sign, mais qui ont leur propre image de signature manuscrite ou électronique.

**Que se passe-t-il si on ne fournit pas d'image ?**
Si vous ne fournissez pas d'image personnalisée pour un signataire externe, le système utilisera automatiquement l'image de signature de la personne qui fait la demande (vous). Si cette personne n'a pas d'image non plus, le système créera automatiquement une signature simple avec le nom du signataire dans un rectangle.

### Données des signataires (signers_data)

**Quelles sont les données minimales à fournir ?**
Vous devez obligatoirement fournir trois informations pour chaque signataire :
- Le nom de famille
- Le prénom  
- La fonction ou le titre de la personne

L'email et le téléphone sont optionnels mais recommandés car ils améliorent la traçabilité juridique du document.

### Paramètres de signature (signature_params)

**Pourquoi les index permettent-ils de faire le lien ?**
Les index servent à dire "ce paramètre concerne le document numéro X et le signataire numéro Y". Par exemple, si vous uploadez 2 documents et avez 3 signataires, vous utilisez les index pour dire "le signataire 1 doit signer sur le document 0 à telle position".

**Peut-on mettre plusieurs signatures sur une même page ?**
Oui, c'est tout à fait possible. Une même personne peut signer plusieurs fois sur la même page, ou vous pouvez avoir plusieurs personnes qui signent sur la même page à des endroits différents.

**Peut-on cibler la dernière page avec -1 ?**
Non, ce n'est pas supporté. Vous devez connaître le nombre exact de pages de votre document et indiquer le numéro réel de la page (par exemple, page 4 pour un document de 5 pages).

**À quoi correspondent les stamp_pages ?**
Les "stamp_pages" servent à apposer des paraphes ou des cachets sur certaines pages, sans faire une signature complète. C'est différent d'une signature : c'est juste pour marquer que la page a été vue ou approuvée.

**Y a-t-il un QR code par signature ?**
Non, les QR codes sont indépendants des signatures. Vous pouvez mettre autant de QR codes que vous voulez, où vous voulez, avec le contenu que vous voulez. Ils ne sont pas automatiquement liés aux signatures.

**Pourquoi voit-on des coordonnées comme 300 alors que vous aviez dit en millimètres sur du A4 ?**
Vous fournissez bien les coordonnées en millimètres comme prévu. Le système fait automatiquement la conversion en arrière-plan pour le traitement interne. Un document A4 fait 210mm de large et 297mm de haut, donc une coordonnée de 300mm serait en dehors du document - c'est pourquoi le système convertit automatiquement vos millimètres vers les unités internes. L'origine des coordonnées commence en bas à gauche du document (pas en haut à gauche).

## Questions sur les retours

### Comptage des signatures

**Pourquoi le retour dit "2 documents signés avec 3 signatures" ?**
Il y a une confusion dans l'exemple. Le système compte le nombre de documents traités, pas le nombre de signatures individuelles. Si vous signez 2 documents, le système compte 2 signatures pour la facturation, même si plusieurs personnes signent sur chaque document. C'est le nombre de documents qui compte, pas le nombre de signataires.

### Structure des erreurs

**Quelle est la structure des erreurs ?**
Toutes les erreurs suivent le même format simple : un message d'erreur en français qui explique exactement ce qui ne va pas.

**A-t-on un message exploitable ?**
Oui, tous les messages d'erreur sont conçus pour être compréhensibles et vous dire exactement quoi corriger. Par exemple : "Le champ 'nom' est manquant pour le signataire 1" ou "Vous avez dépassé la limite de 100 documents par requête".

**Peut-on fournir ces informations à l'utilisateur ?**
Oui, les messages d'erreur sont prévus pour être affichés directement à vos utilisateurs. Ils sont en français et expliquent clairement le problème.

## Récupération des documents signés

### Comment récupérer le document signé

**Sous quelle forme reçoit-on le document ?**
Vous recevez une adresse web (URL) que vous pouvez utiliser pour télécharger le document PDF signé. C'est un fichier PDF normal que vous pouvez ouvrir, imprimer, ou envoyer par email.

### Protection et sécurité

**Comment l'URL est-elle protégée ?**
L'URL contient des codes uniques impossibles à deviner. Même si quelqu'un connaît le début de l'adresse, il ne peut pas deviner les codes spécifiques de votre document. C'est comme avoir une clé très complexe.

**Doit-on utiliser la clé API pour télécharger ?**
Non, une fois que vous avez l'URL, vous pouvez télécharger le document directement sans authentification. L'URL elle-même sert de "pass" pour accéder au document.

**Y a-t-il des paramètres ?**
Non, il suffit d'aller à l'adresse fournie avec un navigateur web ou votre application pour télécharger le fichier PDF.

### Durée de conservation

**Quelle est la durée de rétention du document ?**
Les documents signés ne sont pas conservés indéfiniment. La durée de conservation dépend de la politique de votre organisation et des réglementations en vigueur. Contactez votre administrateur DKB Sign pour connaître la durée de rétention spécifique à votre compte.

## Informations pratiques

### Serveurs disponibles
- **Tests :** `https://staging.dkbsignv3.com/apiDkbSignV3`
- **Production :** `https://dkbsignv3.com/apiDkbSignV3`

### Limites importantes
- Maximum 100 documents par requête
- Les coordonnées sont fournies en millimètres (conversion automatique en arrière-plan)
- L'origine des coordonnées est en bas à gauche du document
- Les numéros de pages commencent à 0 (première page = 0)
- Les index de signataires commencent à 0 (premier signataire = 0)

### Support
Pour toute question supplémentaire, contactez le support technique DKB Solutions qui pourra vous aider avec des exemples concrets adaptés à votre cas d'usage.
