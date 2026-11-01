"""Fixed-stretch RGB and index time series for the August reference parcels.

Optional research dependency: matplotlib. No image enhancement or water labels
are inferred; outlines use the current cadastral master, not a 2023 survey.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from osgeo import gdal, ogr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def outline(ax, geometry, color):
    if geometry.GetGeometryName() in ('LINEARRING', 'LINESTRING'):
        points = np.array(geometry.GetPoints())
        ax.plot(points[:,0], points[:,1], color=color, lw=1)
    else:
        for child in geometry:
            outline(ax, child, color)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    master = json.loads((root/'data/parcel-master.json').read_text())
    refs = ['45137A03300153', '45137A03300155']
    colors = ['#00ffff', '#ff40ff']
    geometries = [ogr.CreateGeometryFromJson(json.dumps(next(f['geometry'] for f in master['features'] if f['refcat'] == ref))) for ref in refs]
    observations = sorted(json.loads(args.report.read_text())['observations'], key=lambda x:x['datetime'])
    fig, axs = plt.subplots(3,5,figsize=(15,11),layout='constrained')
    for ax in axs.flat: ax.axis('off')
    for ax, observation in zip(axs.flat, observations):
        folder = args.raw/observation['product']
        values = []
        for band in ('B04','B03','B02'):
            ds = gdal.Open(str(folder/f'raw_{band}_10m.tif'))
            item = json.loads((folder/'source_item.json').read_text())
            asset = item['assets'][band+'_10m']
            a = ds.ReadAsArray()
            values.append(np.where(a == -9999, np.nan, a*asset['raster:scale']+asset['raster:offset']))
        rgb = np.clip(np.stack(values,axis=-1)/.3,0,1)**(1/1.3)
        gt = ds.GetGeoTransform()
        extent = [gt[0],gt[0]+ds.RasterXSize*10,gt[3]-ds.RasterYSize*10,gt[3]]
        ax.imshow(rgb,extent=extent,interpolation='nearest')
        for geometry,color in zip(geometries,colors): outline(ax,geometry,color)
        quality = '' if observation['status']=='quality_passed' else ' · no evaluable'
        ax.set_title(observation['datetime'][:10]+quality,fontsize=10)
        if observation['datetime'][:10] == '2023-08-16':
            detail, panel = plt.subplots(figsize=(7, 7), layout='constrained')
            panel.imshow(rgb, extent=extent, interpolation='nearest')
            for ref, geometry, color in zip(refs, geometries, colors):
                outline(panel, geometry, color)
                point = geometry.Centroid()
                panel.text(point.GetX(), point.GetY(), ref[-3:], color=color,
                           ha='center', weight='bold', fontsize=14,
                           bbox={'facecolor':'black', 'alpha':.5, 'edgecolor':'none'})
            panel.axis('off')
            panel.set_title('Sentinel-2 RGB · 16/08/2023 · norte arriba\n153: cian · 155: magenta')
            detail.text(.5, -.035, 'RGB 0–0,30 · gamma 1,3 · contornos del maestro actual\nEl color por sí solo no delimita el agua bajo la vegetación.',
                        ha='center', fontsize=9)
            detail.savefig(args.output/'august-16-rgb.jpg', dpi=160, bbox_inches='tight')
            plt.close(detail)
    axs.flat[-1].text(0,.7,'153: cian\n155: magenta\nNorte arriba\nRGB fijo 0–0,30\nGamma 1,3\nSin máscara de agua dibujada',fontsize=12)
    fig.suptitle('Sentinel-2 · agosto de 2023 · vegetación sobre el encharcamiento referido\nLos cambios de color no identifican por sí solos el agua bajo el cultivo',fontsize=14)
    fig.savefig(args.output/'august-rgb.jpg',dpi=160)
    plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(13,4),layout='constrained')
    for ax,name in zip(axs,['NDVI','NDWI','MNDWI']):
        for ref,color in zip(refs,['#007b83','#9b278d']):
            values=[o['parcels'][ref]['indices'][name]['median'] for o in observations]
            ax.plot([int(o['datetime'][8:10]) for o in observations],values,'o-',color=color,label=ref[-3:])
        ax.axhline(0,color='grey',lw=.6);ax.set_ylim(-1,1);ax.set_title(name+' · mediana parcelaria')
        ax.set_xlabel('Día de agosto de 2023');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Huecos: observaciones no evaluables (26 y 29). Las series no delimitan superficie inundada.')
    fig.savefig(args.output/'august-indices.png',dpi=160)


if __name__ == '__main__': main()
