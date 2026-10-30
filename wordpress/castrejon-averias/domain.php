<?php
// Pure validation helpers, independently testable without bootstrapping WordPress.
require_once __DIR__ . '/location.php';
function ca_uuid($value) {
    return is_string($value) && preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D', $value);
}
function ca_validate($input) {
    if (!is_array($input)) { throw new InvalidArgumentException('Formulario incorrecto.'); }
    $keys = ['id', 'kind', 'element', 'description', 'priority', 'observed_at', 'longitude', 'latitude', 'location_source', 'accuracy_m', 'photo_base64'];
    if (array_diff(array_keys($input), $keys)) { throw new InvalidArgumentException('El formulario contiene campos no admitidos.'); }
    if (!ca_uuid($input['id'] ?? null)) { throw new InvalidArgumentException('Identificador incorrecto.'); }
    $data = ['id' => $input['id']];
    foreach (['kind' => ['fuga', 'rotura', 'obstruccion', 'electrica', 'otra'], 'priority' => ['normal', 'alta', 'urgente'], 'location_source' => ['gps', 'manual']] as $key => $allowed) {
        if (!in_array($input[$key] ?? null, $allowed, true)) { throw new InvalidArgumentException('Revisa tipo, prioridad y origen de ubicación.'); }
        $data[$key] = $input[$key];
    }
    foreach (['element' => 120, 'description' => 2000] as $key => $max) {
        $text = $input[$key] ?? '';
        if (!is_string($text) || preg_match('/[\x00-\x08\x0B\x0C\x0E-\x1F]/', $text) || mb_strlen($text) > $max || ($key === 'description' && mb_strlen(trim($text)) < 5)) {
            throw new InvalidArgumentException('Descripción o elemento incorrectos.');
        }
        $data[$key] = trim($text);
    }
    ca_location_validate($input);
    foreach (['longitude', 'latitude'] as $key) {
        $data[$key] = (float) $input[$key];
    }
    $accuracy = $input['accuracy_m'] ?? null;
    $data['accuracy_m'] = $data['location_source'] === 'manual' ? null : $accuracy;
    $date = $input['observed_at'] ?? null;
    if (!is_string($date) || !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?Z$/D', $date) ||
        strtotime($date) === false || strtotime($date) > time() + 300 || strtotime($date) < strtotime('2000-01-01T00:00:00Z')) {
        throw new InvalidArgumentException('Fecha incorrecta o futura.');
    }
    $data['observed_at'] = $date;
    $parsed = new DateTimeImmutable($date);
    if ($parsed->format('Y-m-d\TH:i:s') !== substr($date, 0, 19)) { throw new InvalidArgumentException('La fecha no existe en el calendario.'); }
    return $data;
}
function ca_photo($encoded) {
    if (!is_string($encoded) || strlen($encoded) > 2700000) { throw new InvalidArgumentException('Falta la fotografía o supera 2 MB.'); }
    $raw = base64_decode($encoded, true);
    if ($raw === false || strlen($raw) > 2000000) { throw new InvalidArgumentException('Fotografía incorrecta.'); }
    $info = @getimagesizefromstring($raw);
    if (!$info || !in_array($info[2], [IMAGETYPE_JPEG, IMAGETYPE_PNG, IMAGETYPE_WEBP], true) || $info[0] * $info[1] > 16000000) {
        throw new InvalidArgumentException('Usa una foto JPEG, PNG o WebP de hasta 16 megapíxeles.');
    }
    $source = @imagecreatefromstring($raw);
    if (!$source) { throw new InvalidArgumentException('No se pudo abrir la fotografía.'); }
    $scale = min(1, 1600 / max($info[0], $info[1]));
    $width = max(1, (int) round($info[0] * $scale)); $height = max(1, (int) round($info[1] * $scale));
    $clean = imagecreatetruecolor($width, $height);
    imagefill($clean, 0, 0, imagecolorallocate($clean, 255, 255, 255));
    imagecopyresampled($clean, $source, 0, 0, 0, 0, $width, $height, $info[0], $info[1]);
    ob_start(); imagejpeg($clean, null, 82); $result = ob_get_clean();
    imagedestroy($source); imagedestroy($clean);
    if (!$result || strlen($result) > 2000000) { throw new InvalidArgumentException('Reduce el tamaño de la fotografía.'); }
    return $result;
}
