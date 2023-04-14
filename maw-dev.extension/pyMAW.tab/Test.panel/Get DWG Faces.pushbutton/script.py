# Pick a DWG import instance, extract faces 
# from it visible in the current view and create
# extrusions from them.

import clr


#Load Revit API

from pyrevit import revit, DB
from pyrevit import forms
from pyrevit import script

doc = __revit__.ActiveUIDocument.Document
view = doc.ActiveView

dwg_geo = []


# Pick Import Instance

revit.get_selection()
selection_filter = \
            [x for x in revit.query.get_types_by_class(DB.ImportInstance,
                                                       doc=revit.doc)]
selection.set_to(list(selection_filter))

dwg = doc.GetElement( selection )

# Get Geometry

# geo = dwg.get_Geometry( )

# foreach( var go in ge )
    # {
      # if( go is GeometryInstance )
      # {
        # var gi = go as GeometryInstance;

        # var ge2 = gi.GetInstanceGeometry();

        # if( ge2 != null )
        # {
          # foreach( var obj in ge2 )
          # {
            # // Only work on PolyLines

            # if( obj is PolyLine )
            # {
              # // Use the GraphicsStyle to get the 
              # // DWG layer linked to the Category 
              # // for visibility.

              # var gStyle = doc.GetElement( 
                # obj.GraphicsStyleId ) as GraphicsStyle;

              # // Check if the layer is visible in the view.

              # if( !active_view.GetCategoryHidden(
                # gStyle.GraphicsStyleCategory.Id ) )
              # {
                # visible_dwg_geo.Add( obj );
              # }
            # }
          # }
        # }
      # }
    # }

# # Do something with the info

    # if( visible_dwg_geo.Count > 0 )
    # {
      # // Retrieve first filled region type

      # var filledType = new FilteredElementCollector( doc )
        # .WhereElementIsElementType()
        # .OfClass( typeof( FilledRegionType ) )
        # .OfType<FilledRegionType>()
        # .First();

      # using( var t = new Transaction( doc ) )
      # {
        # t.Start( "ProcessDWG" );

        # foreach( var obj in visible_dwg_geo )
        # {
          # var poly = obj as PolyLine;

          # // Draw a filled region for each polyline

          # if( null != poly )
          # {
            # // Create loops for detail region

            # var curveLoop = new CurveLoop();

            # var points = poly.GetCoordinates();

            # for( int i = 0; i < points.Count - 1; ++i )
            # {
              # curveLoop.Append( Line.CreateBound( 
                # points[i], points[i + 1] ) );
            # }

            # FilledRegion.Create( doc, 
              # filledType.Id, active_view.Id, 
              # new List<CurveLoop>() { curveLoop } );
          # }
        # }
      # }
    # }
  # }
