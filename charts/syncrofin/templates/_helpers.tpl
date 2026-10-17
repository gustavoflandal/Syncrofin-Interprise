{{/*
Expand the name of the chart.
*/}}
{{- define "syncrofin.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "syncrofin.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "syncrofin.labels" -}}
helm.sh/chart: {{ include "syncrofin.chart" . }}
app.kubernetes.io/name: {{ include "syncrofin.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "syncrofin.selectorLabels" -}}
app.kubernetes.io/name: {{ include "syncrofin.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "syncrofin.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "syncrofin.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "syncrofin.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Compute the frontend URL based on global.domain and global.tls
*/}}
{{- define "syncrofin.frontendUrl" -}}
{{- if .Values.global.tls -}}
https://{{ .Values.global.domain }}
{{- else -}}
http://{{ .Values.global.domain }}
{{- end -}}
{{- end -}}

{{/*
Compute the default OAuth Redirect URI
*/}}
{{- define "syncrofin.oauthRedirectUri" -}}
{{ include "syncrofin.frontendUrl" . }}/oauth/callback
{{- end -}}

{{/*
Credentials for pulling the SyncroFin images. The Enterprise images are private (ghcr.io), so a cluster
needs a pull secret: kubectl create secret docker-registry ghcr --docker-server=ghcr.io ...
and imagePullSecrets: [{name: ghcr}] in values.
*/}}
{{- define "syncrofin.imagePullSecrets" -}}
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}
