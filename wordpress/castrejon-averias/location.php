<?php
// Advisory QA only. The pending reference is never a geographic permission.
function ca_location_validate($value) {
    if (!is_array($value)) { throw new InvalidArgumentException('Ubicación incorrecta.'); }
    foreach (['longitude' => 180, 'latitude' => 90] as $key => $max) {
        $number = $value[$key] ?? null;
        if ((!is_int($number) && !is_float($number)) || !is_finite((float)$number) || abs($number) > $max) {
            throw new InvalidArgumentException('Coordenadas imposibles. Usa longitud y latitud WGS 84 en grados decimales.');
        }
    }
    $source = $value['location_source'] ?? null;
    $accuracy = $value['accuracy_m'] ?? null;
    if (!in_array($source, ['gps', 'manual'], true) || ($source === 'gps' &&
        ((!is_int($accuracy) && !is_float($accuracy)) || !is_finite((float)$accuracy) || $accuracy < 0 || $accuracy > 100000))) {
        throw new InvalidArgumentException('Revisa la ubicación y su precisión.');
    }
}
function ca_in_ring($x, $y, $ring) {
    $inside = false;
    for ($i = 0, $j = count($ring)-1; $i < count($ring); $j = $i++) {
        [$ax, $ay] = $ring[$j]; [$bx, $by] = $ring[$i];
        if (abs(($x-$ax)*($by-$ay)-($y-$ay)*($bx-$ax)) <= 1e-12 &&
            $x >= min($ax,$bx)-1e-12 && $x <= max($ax,$bx)+1e-12 && $y >= min($ay,$by)-1e-12 && $y <= max($ay,$by)+1e-12) {
            return ['inside' => true, 'boundary' => true];
        }
        if (($ay > $y) !== ($by > $y) && $x < ($bx-$ax)*($y-$ay)/($by-$ay)+$ax) { $inside = !$inside; }
    }
    return ['inside' => $inside, 'boundary' => false];
}
function ca_in_reference($x, $y, $policy) {
    $rings = $policy['geometry']['coordinates']; $outer = ca_in_ring($x,$y,$rings[0]);
    if ($outer['boundary']) { return true; }
    if (!$outer['inside']) { return false; }
    foreach (array_slice($rings,1) as $hole) {
        $hit = ca_in_ring($x,$y,$hole);
        if ($hit['boundary']) { return true; }
        if ($hit['inside']) { return false; }
    }
    return true;
}
function ca_in_envelope($x, $y, $policy) {
    [$w,$s,$e,$n] = $policy['bbox']; $m = $policy['far_margin_degrees'];
    return $x >= $w-$m && $x <= $e+$m && $y >= $s-$m && $y <= $n+$m;
}
function ca_location_quality($value) {
    ca_location_validate($value);
    static $policy = null;
    if ($policy === null) { $policy = json_decode(file_get_contents(__DIR__.'/location-policy.json'),true,512,JSON_THROW_ON_ERROR); }
    $x = $value['longitude']; $y = $value['latitude']; $warnings = [];
    $severity = 'ok'; $status = 'inside_reference';
    $add = function($code,$message) use (&$warnings) { $warnings[] = ['code' => $code, 'message' => $message]; };
    if (!ca_in_envelope($x,$y,$policy)) {
        $status = 'far_from_reference'; $severity = 'danger';
        $add('far_from_reference','Punto muy alejado del ámbito de referencia de Castrejón. Revisa el GPS, los ejes y el signo de las coordenadas antes de publicar.');
        if (ca_in_envelope($y,$x,$policy)) { $add('possible_axis_swap','Posible intercambio de latitud y longitud. No se han corregido automáticamente.'); }
        if (ca_in_envelope(-$x,$y,$policy)) { $add('possible_longitude_sign','Posible signo incorrecto de la longitud. En Castrejón la longitud es negativa.'); }
    } elseif (!ca_in_reference($x,$y,$policy)) {
        $status = 'outside_reference'; $severity = 'warning';
        $add('outside_reference','Punto fuera del perímetro regable de referencia, pendiente de ajuste. Puede corresponder a una infraestructura del canal: comprueba el lugar y confirma si es correcto.');
    }
    if ($value['location_source'] === 'manual') {
        if ($severity === 'ok') { $severity = 'notice'; }
        $add('manual_location','Ubicación manual, sin precisión GPS. Comprueba el punto del mapa y las coordenadas.');
    } elseif ($value['accuracy_m'] == 0 || $value['accuracy_m'] > $policy['gps_warning_m']) {
        if ($severity !== 'danger') { $severity = 'warning'; }
        $add($value['accuracy_m'] == 0 ? 'gps_accuracy_unknown' : 'gps_low_accuracy', $value['accuracy_m'] == 0 ?
            'El GPS informa de precisión cero; no se considera una posición exacta. Repite el GPS o sitúa el punto manualmente.' :
            'Precisión GPS insuficiente (±'.round($value['accuracy_m']).' m; aviso por encima de '.$policy['gps_warning_m'].' m). Repite el GPS a cielo abierto o corrige el punto manualmente.');
    }
    return ['policy_version'=>$policy['version'],'reference_status'=>$policy['status'],'status'=>$status,'severity'=>$severity,'warnings'=>$warnings];
}
